from app.config.settings import Settings

settings = Settings()


def get_descr_as_str(
    descriptions,
    preferred_languages_descriptions=settings.prefered_languages_descriptions,
):
    # TODO: implement deepseek call to pick best description
    descr_text = ""
    for lang in preferred_languages_descriptions:
        for desc in descriptions:
            if desc.language == lang:
                descr_text = desc.text
    return "N/A" if not descr_text else descr_text
