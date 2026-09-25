async def import_user_data(payload: ImportRequest, request: Request) -> dict[str, Any]:
    await _enforce_rate_limit(request, "data-import", _RATE_LIMIT_DATA)
    st, _, _ = _require_runtime()
    ok, warnings = validate_bundle(payload.bundle)
    if not ok:
        logger.warning(
            "[NEXO_DEBUG_IMPORT] invalid_bundle warnings=%s message_count=%s",
            list(warnings),
            len(payload.bundle.get("messages", [])) if isinstance(payload.bundle.get("messages", []), list) else -1,
        )
        raise HTTPException(status_code=400, detail={"reason": "invalid_bundle", "warnings": list(warnings)})
    messages = payload.bundle.get("messages", [])
    if len(messages) > _MAX_IMPORT_MESSAGES:
        raise HTTPException(status_code=413, detail={"reason": "import_too_large"})
    try:
        accepted = await st.import_replication_batch(messages, enqueue_replication=payload.replicate)
    except ReplicationConflictError as exc:
        logger.warning("[NEXO_DEBUG_IMPORT] conflict detail=%s", str(exc)[:500])
        raise HTTPException(status_code=409, detail={"reason": "import_conflict", "detail": str(exc)}) from exc
    except ValueError as exc:
        logger.warning("[NEXO_DEBUG_IMPORT] invalid_message detail=%s", str(exc)[:500])
        raise HTTPException(status_code=400, detail={"reason": "invalid_import_message", "detail": str(exc)}) from exc
    return {
        "status": "ok",
        "schema_version": payload.bundle.get("schema_version"),
        "user_id": payload.bundle.get("user_id"),