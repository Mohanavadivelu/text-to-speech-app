"""Languages and voices supported by hexgrad/Kokoro-82M (v1.0).

Grades are the overall quality grades from the model card. Gender comes from
the second letter of the voice id (f = female, m = male).
"""

LANG_CODES = {
    "American English": "a",
    "British English":  "b",
    "Hindi":            "h",
    "French":           "f",
    "Italian":          "i",
    "Spanish":          "e",
    "Br. Portuguese":   "p",
}

DEFAULT_LANGUAGE = "American English"

# (voice_id, display name, quality grade or None)
_VOICE_DATA = {
    "American English": [
        ("af_heart", "Heart", "A"), ("af_bella", "Bella", "A-"), ("af_nicole", "Nicole", "B-"),
        ("af_aoede", "Aoede", "C+"), ("af_kore", "Kore", "C+"), ("af_sarah", "Sarah", "C+"),
        ("af_alloy", "Alloy", "C"), ("af_nova", "Nova", "C"), ("af_sky", "Sky", "C-"),
        ("am_fenrir", "Fenrir", "C+"), ("am_michael", "Michael", "C+"), ("am_puck", "Puck", "C+"),
        ("am_echo", "Echo", "D"), ("am_eric", "Eric", "D"), ("am_liam", "Liam", "D"),
        ("am_adam", "Adam", "F+"),
    ],
    "British English": [
        ("bf_emma", "Emma", "B-"), ("bf_isabella", "Isabella", "C"), ("bf_alice", "Alice", "D"),
        ("bf_lily", "Lily", "D"), ("bm_fable", "Fable", "C"), ("bm_george", "George", "C"),
        ("bm_lewis", "Lewis", "D+"), ("bm_daniel", "Daniel", "D"),
    ],
    "Hindi": [
        ("hf_alpha", "Alpha", "C"), ("hf_beta", "Beta", "C"),
        ("hm_omega", "Omega", "C"), ("hm_psi", "Psi", "C"),
    ],
    "French": [("ff_siwis", "Siwis", "B-")],
    "Italian": [("if_sara", "Sara", "C"), ("im_nicola", "Nicola", "C")],
    "Spanish": [("ef_dora", "Dora", None), ("em_alex", "Alex", None), ("em_santa", "Santa", None)],
    "Br. Portuguese": [("pf_dora", "Dora", None), ("pm_alex", "Alex", None), ("pm_santa", "Santa", None)],
}


def voice_label(voice_id: str, name: str, grade) -> str:
    gender = "Female" if voice_id[1:2] == "f" else "Male"
    return f"{name} · {gender} · Grade {grade}" if grade else f"{name} · {gender}"


# lang -> [(voice_id, label)] — the shape the UI consumes
VOICES = {
    lang: [(vid, voice_label(vid, name, grade)) for vid, name, grade in voices]
    for lang, voices in _VOICE_DATA.items()
}


# Short sample sentence per language for the voice preview button
PREVIEW_TEXT = {
    "American English": "Hi there! This is how my voice sounds.",
    "British English":  "Hello there! This is how my voice sounds.",
    "Hindi":            "नमस्ते! मेरी आवाज़ ऐसी सुनाई देती है।",
    "French":           "Bonjour ! Voici à quoi ressemble ma voix.",
    "Italian":          "Ciao! Ecco come suona la mia voce.",
    "Spanish":          "¡Hola! Así es como suena mi voz.",
    "Br. Portuguese":   "Olá! É assim que a minha voz soa.",
}


def default_voice(lang: str) -> str:
    voices = VOICES.get(lang) or VOICES[DEFAULT_LANGUAGE]
    return voices[0][0]
