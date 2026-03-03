_SETTING_KEY_GEMINI_MODEL = "gemini_model"


def settings_page(
    *,
    request_obj,
    flash_fn,
    redirect_fn,
    url_for_fn,
    render_template_fn,
    app_obj,
):
    resolve_gemini_model_fn = app_obj.extensions["resolve_gemini_model_fn"]
    persist_gemini_model_fn = app_obj.extensions["persist_gemini_model_fn"]
    resolve_gemini_api_key_fn = app_obj.extensions["resolve_gemini_api_key_fn"]
    persist_gemini_api_key_fn = app_obj.extensions["persist_gemini_api_key_fn"]
    clear_gemini_api_key_fn = app_obj.extensions["clear_gemini_api_key_fn"]
    gemini_api_key_store_available_fn = app_obj.extensions["gemini_api_key_store_available_fn"]
    gemini_api_key_store_mode_fn = app_obj.extensions["gemini_api_key_store_mode_fn"]
    gemini_api_key_store_uses_alt_fallback_fn = app_obj.extensions[
        "gemini_api_key_store_uses_alt_fallback_fn"
    ]

    selectable_models = list(app_obj.config.get("GEMINI_SELECTABLE_MODELS", []))
    current_model = str(resolve_gemini_model_fn() or app_obj.config.get("GEMINI_MODEL", "")).strip()
    store_mode = str(gemini_api_key_store_mode_fn() or "").strip().lower()
    is_database_mode = store_mode.startswith("database")

    if request_obj.method == "POST":
        selected_model = str(request_obj.form.get("gemini_model", "")).strip()
        api_key = str(request_obj.form.get("gemini_api_key", "")).strip()
        clear_api_key = request_obj.form.get("clear_gemini_api_key") == "1"

        if selected_model not in selectable_models:
            flash_fn("Selected Gemini model is invalid.", "error")
            return redirect_fn(url_for_fn("settings"))
        if api_key and clear_api_key:
            flash_fn("Provide a new API key or choose clear, not both.", "error")
            return redirect_fn(url_for_fn("settings"))

        persist_gemini_model_fn(selected_model)
        if not is_database_mode:
            app_obj.config["GEMINI_MODEL"] = selected_model
        flash_fn(f"Saved Gemini model: {selected_model}", "success")

        if api_key:
            if not is_database_mode:
                # For local keyring mode, keep runtime behavior compatible with legacy flow.
                app_obj.config["GEMINI_API_KEY"] = api_key
            ok, error = persist_gemini_api_key_fn(api_key)
            if not ok:
                if is_database_mode:
                    flash_fn(error or "Could not save Gemini API key.", "error")
                else:
                    flash_fn(
                        (error or "Could not save Gemini API key.")
                        + " The key is active for this running app only.",
                        "error",
                    )
            else:
                if store_mode.startswith("database"):
                    flash_fn("Gemini API key saved in database storage.", "success")
                elif gemini_api_key_store_uses_alt_fallback_fn():
                    flash_fn(
                        "Gemini API key saved using keyrings.alt local fallback storage.",
                        "info",
                    )
                else:
                    flash_fn("Gemini API key saved in secure local storage.", "success")
        elif clear_api_key:
            ok, error = clear_gemini_api_key_fn()
            if not ok:
                flash_fn(error or "Could not clear Gemini API key.", "error")
            else:
                if not is_database_mode:
                    app_obj.config["GEMINI_API_KEY"] = ""
                if store_mode.startswith("database"):
                    flash_fn("Gemini API key removed from database storage.", "success")
                elif gemini_api_key_store_uses_alt_fallback_fn():
                    flash_fn("Gemini API key removed from keyrings.alt fallback storage.", "success")
                else:
                    flash_fn("Gemini API key removed from secure local storage.", "success")

        return redirect_fn(url_for_fn("settings"))

    stored_api_key = resolve_gemini_api_key_fn()
    has_stored_api_key = bool(stored_api_key)
    has_runtime_api_key = bool(str(app_obj.config.get("GEMINI_API_KEY", "")).strip())
    keyring_backend_mode = store_mode
    current_key_source = "none"
    if has_stored_api_key:
        if keyring_backend_mode.startswith("database"):
            current_key_source = "database"
        elif keyring_backend_mode == "keyrings_alt":
            current_key_source = "keyrings_alt_fallback"
        else:
            current_key_source = "secure_local_storage"
    elif has_runtime_api_key:
        current_key_source = "environment"

    return render_template_fn(
        "settings.html",
        selectable_models=selectable_models,
        current_model=current_model,
        current_model_supported=current_model in selectable_models,
        keyring_available=bool(gemini_api_key_store_available_fn()),
        keyring_backend_mode=keyring_backend_mode,
        has_stored_api_key=has_stored_api_key,
        current_key_source=current_key_source,
    )
