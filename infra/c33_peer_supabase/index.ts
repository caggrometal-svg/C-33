import { withSupabase } from "npm:@supabase/server";

const MAX_BODY=2_000_000, MAX_BATCH=250, SCHEMA="c33_peer", TABLE="messages", CONFIG="config";
const encoder=new TextEncoder();
const canonical=(v)=>Array.isArray(v)?v.map(canonical):(v&&typeof v==="object"?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v);
const hex=(bytes)=>Array.from(new Uint8Array(bytes)).map(b=>b.toString(16).padStart(2,"0")).join("");
const sha256=async(bytes)=>hex(await crypto.subtle.digest("SHA-256",bytes));
const hmac256=async(secret,bytes)=>{
  const key=await crypto.subtle.importKey("raw",encoder.encode(secret),{name:"HMAC",hash:"SHA-256"},false,["sign"]);
  return hex(await crypto.subtle.sign("HMAC",key,bytes));
};
const equalConst=(a,b)=>{if(!a||!b||a.length!==b.length)return false;let d=0;for(let i=0;i<a.length;i++)d|=a.charCodeAt(i)^b.charCodeAt(i);return d===0};
const response=(body,status=200)=>new Response(JSON.stringify(body),{status,headers:{"Content-Type":"application/json","Cache-Control":"no-store"}});
const integrity=async(db)=>{
  const {data,error}=await db.from(TABLE).select("id,conversation_id,user_id,seq,role,content,metadata,request_id,created_at").order("id",{ascending:true}).range(0,4999);
  if(error)throw new Error("integrity_query_failed:"+error.message);
  const rows=data??[], ids=[], msgs=[];
  for(const row of rows){
    const id=String(row.id); ids.push(encoder.encode(id),encoder.encode("\n"));
    const record={id,conversation_id:String(row.conversation_id),user_id:String(row.user_id),seq:Number(row.seq),role:String(row.role),content:String(row.content),metadata:row.metadata&&typeof row.metadata==="object"?row.metadata:{},request_id:row.request_id==null?null:String(row.request_id),created_at:String(row.created_at)};
    msgs.push(encoder.encode(JSON.stringify(canonical(record))),encoder.encode("\n"));
  }
  const join=(parts)=>{const n=parts.reduce((a,p)=>a+p.length,0),o=new Uint8Array(n);let i=0;for(const p of parts){o.set(p,i);i+=p.length}return o};
  return {total_messages:rows.length,unique_message_ids:new Set(rows.map(r=>String(r.id))).size,message_id_digest:await sha256(join(ids)),message_digest:await sha256(join(msgs))};
};
export default {fetch:withSupabase({auth:"none"},async(req,ctx)=>{
  const path=new URL(req.url).pathname, db=ctx.supabaseAdmin.schema(SCHEMA);
  if(req.method==="GET"&&path.endsWith("/health"))return response({status:"alive",service:"C-33",deployment_sha:Deno.env.get("SB_EXECUTION_ID")??"supabase-peer",role:"secondary"});
  if(req.method==="GET"&&path.endsWith("/ready")){
    const {data,error}=await db.from(CONFIG).select("value").eq("key","replication_hmac_secret").maybeSingle();
    if(error||!data?.value)return response({status:"not_ready",service:"C-33",database:"error"},503);
    return response({status:"ready",service:"C-33",deployment_sha:Deno.env.get("SB_EXECUTION_ID")??"supabase-peer",database:"ok",peer_configured:false,provider_count:0});
  }
  if(req.method==="GET"&&path.endsWith("/replication/status"))return response({status:"ok",service:"C-33",deployment_sha:Deno.env.get("SB_EXECUTION_ID")??"supabase-peer",backend_role:"secondary",peer_url_configured:false,peer_status:"NOT_CONFIGURED",replication_pending:0,...(await integrity(db)),quiesced:true});
  if(req.method!=="POST"||!path.endsWith("/internal/replicate"))return response({detail:"not_found"},404);
  if(req.headers.get("x-c33-replication-version")!=="1")return response({detail:"unsupported_replication_version"},400);
  const raw=new Uint8Array(await req.arrayBuffer());
  if(raw.length>MAX_BODY)return response({detail:"replication_payload_too_large"},413);
  const {data:secretRow,error:secretError}=await db.from(CONFIG).select("value").eq("key","replication_hmac_secret").maybeSingle();
  if(secretError||!secretRow?.value)return response({detail:"replication_secret_unavailable"},503);
  const supplied=req.headers.get("x-c33-replication-signature")??"", expected=await hmac256(String(secretRow.value),raw);
  if(!equalConst(supplied,expected))return response({detail:"invalid_replication_signature"},401);
  let body;try{body=JSON.parse(new TextDecoder().decode(raw))}catch{return response({detail:"invalid_replication_payload"},400)}
  const messages=body?.messages;
  if(!Array.isArray(messages)||messages.length>MAX_BATCH)return response({detail:"invalid_replication_batch"},400);
  const ids=messages.map(m=>String(m?.id??""));
  if(ids.some(id=>!id)||new Set(ids).size!==ids.length)return response({detail:"invalid_replication_message_ids"},400);
  const {data:existing,error:readError}=await db.from(TABLE).select("id,conversation_id,user_id,seq,role,content,metadata,request_id,created_at").in("id",ids);
  if(readError)return response({detail:"existing_query_failed:"+readError.message},502);
  const byId=new Map((existing??[]).map(m=>[String(m.id),m])), normalized=[];
  for(const m of messages){
    const item={id:String(m.id),conversation_id:String(m.conversation_id),user_id:String(m.user_id),seq:Number(m.seq),role:String(m.role),content:String(m.content),metadata:m.metadata&&typeof m.metadata==="object"?m.metadata:{},request_id:m.request_id==null?null:String(m.request_id),created_at:String(m.created_at)};
    normalized.push(item); const old=byId.get(item.id);
    if(old&&JSON.stringify(canonical(old))!==JSON.stringify(canonical(item)))return response({detail:"message_id_conflict:"+item.id},409);
  }
  const missing=normalized.filter(m=>!byId.has(m.id));
  if(missing.length){const {error:insertError}=await db.from(TABLE).insert(missing);if(insertError)return response({detail:"replication_insert_failed:"+insertError.message},502);}
  return response({status:"ok",accepted:normalized.length,received:normalized.length,accepted_ids:ids,receipt_sha256:await sha256(raw)});
})};