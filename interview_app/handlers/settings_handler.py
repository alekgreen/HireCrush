from interview_app.services import secure_token_store

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
    settings_repository = app_obj.extensions["settings_repository"]
    selectable_models = list(app_obj.config.get("GEMINI_SELECTABLE_MODELS", []))
    current_model = str(app_obj.config.get("GEMINI_MODEL", "")).strip()

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

        settings_repository.set_value(_SETTING_KEY_GEMINI_MODEL, selected_model)
        app_obj.config["GEMINI_MODEL"] = selected_model
        flash_fn(f"Saved Gemini model: {selected_model}", "success")

        if api_key:
            # Always enable the provided key for the current process, even if secure persistence fails.
            app_obj.config["GEMINI_API_KEY"] = api_key
            ok, error = secure_token_store.set_gemini_api_key(api_key)
            if not ok:
                flash_fn(
                    (error or "Could not save Gemini API key.")
                    + " The key is active for this running app only.",
                    "error",
                )
            else:
                if secure_token_store.using_keyrings_alt_fallback():
                    flash_fn(
                        "Gemini API key saved using keyrings.alt local fallback storage.",
                        "info",
                    )
                else:
                    flash_fn("Gemini API key saved in secure local storage.", "success")
        elif clear_api_key:
            ok, error = secure_token_store.clear_gemini_api_key()
            if not ok:
                flash_fn(error or "Could not clear Gemini API key.", "error")
            else:
                app_obj.config["GEMINI_API_KEY"] = ""
                if secure_token_store.using_keyrings_alt_fallback():
                    flash_fn("Gemini API key removed from keyrings.alt fallback storage.", "success")
                else:
                    flash_fn("Gemini API key removed from secure local storage.", "success")

        return redirect_fn(url_for_fn("settings"))

    stored_api_key = secure_token_store.get_gemini_api_key()
    has_stored_api_key = bool(stored_api_key)
    has_runtime_api_key = bool(str(app_obj.config.get("GEMINI_API_KEY", "")).strip())
    keyring_backend_mode = secure_token_store.backend_mode()
    current_key_source = "none"
    if has_stored_api_key:
        if keyring_backend_mode == "keyrings_alt":
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
        keyring_available=secure_token_store.keyring_available(),
        keyring_backend_mode=keyring_backend_mode,
        has_stored_api_key=has_stored_api_key,
        current_key_source=current_key_source,
    )
