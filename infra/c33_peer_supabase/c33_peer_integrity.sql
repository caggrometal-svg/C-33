CREATE OR REPLACE FUNCTION public.c33_peer_integrity()
RETURNS jsonb
LANGUAGE sql
STABLE
SET search_path TO 'pg_catalog', 'public'
AS $function$
  WITH ordered AS (
    SELECT
      id,
      jsonb_build_object(
        'id', id,
        'conversation_id', btrim(conversation_id),
        'user_id', btrim(user_id),
        'seq', seq,
        'role', btrim(role),
        'content', btrim(content),
        'metadata', coalesce(metadata, '{}'::jsonb),
        'request_id', nullif(btrim(request_id), ''),
        'created_at', created_at::timestamptz
      )::text AS record_json
    FROM c33_peer.messages
  ),
  aggregate_data AS (
    SELECT
      count(*)::integer AS total_messages,
      count(distinct id)::integer AS unique_message_ids,
      coalesce(string_agg(id || E'\n', '' ORDER BY id::uuid), '') AS id_data,
      coalesce(string_agg(record_json || E'\n', '' ORDER BY id::uuid), '') AS message_data
    FROM ordered
  )
  SELECT jsonb_build_object(
    'total_messages', total_messages,
    'unique_message_ids', unique_message_ids,
    'message_id_digest', encode(extensions.digest(convert_to(id_data,'UTF8'),'sha256'),'hex'),
    'message_digest', encode(extensions.digest(convert_to(message_data,'UTF8'),'sha256'),'hex')
  )
  FROM aggregate_data;
$function$;
