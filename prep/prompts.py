"""LLM prompts for the prep steps. Edit here to change how notes are read or the transcript is cleaned."""

CONTEXT = """You prepare background notes for editing a podcast episode into short clips. Shows and languages vary;
some episodes are an interview, some a relaxed chat between several people.
You get whatever material the producer dropped in: episode descriptions, topic notes, links, sometimes rough subtitles.

Return:
- brief: 2–4 sentences, in the episode's language, on who the guests are and what the episode covers.
- speakers: the people who talk in the episode, host first, with exact spelling of their names.
- host: the one who hosts / leads the conversation (exact name as in speakers).
- language: the language mostly SPOKEN in the episode as an ISO 639-1 code ("en", "de", "sl", …). Notes can be in
  another language than the conversation, so judge by who talks.
- glossary: every proper noun and technical term a speech recogniser might mangle — people, companies, projects,
  products, institutions, places, acronyms — with exact canonical spelling and casing (e.g. "Hugging Face",
  "PostgreSQL"). Use base (uninflected) forms. 20–150 items. No generic words.
- slug: 1–2 lowercase words identifying the episode (guest surname or main topic), ascii, hyphen-separated."""

CLEAN = """You correct automatic speech-recognition output for a podcast so it can be used as subtitles.

Rules:
- Keep each cue in the language it was spoken in. Never translate.
- Fix misheard names and terms using the glossary. In inflected languages, inflect names and terms correctly.
- Fix obvious mis-recognitions, spelling, casing and punctuation, with that language's sentence case and punctuation.
- Keep the speaker's words and spoken style. Do NOT paraphrase, summarise, translate or make it more formal. Keep
  technical terms as said.
- Remove pure fillers and false starts that add nothing ("uh", "um", "erm", doubled words, and their equivalents in
  the cue's language), but keep colloquial words that carry tone ("you know", "right", "like").
- The first time a product, project, institution or piece of jargon comes up that a general viewer may not know, add
  a short clarification in parentheses right after it, in the cue's language, e.g. "LoRA (a light way to fine-tune
  models)". Keep it to 2–6 words, factual, from the glossary/brief or common knowledge. Don't repeat a clarification
  that already appears in the previous context. Roughly 5–15 per hour of conversation; skip the obvious ones (Google,
  ChatGPT).
- Return every cue id you were given, in order, with ITS OWN corrected text. Each cue keeps exactly the words spoken in
  that cue: never move words to a neighbouring cue, never merge or split cues, even mid-sentence."""

SPEAKERS = ("Map diarization speaker ids (S1, S2, …) to real names. The host introduces the show and asks most of the "
            "questions (see the questions per 1000 words) and usually talks less; guests answer at length. Names said "
            "in the conversation help: someone addressed by name is not the one speaking. Use 'Unknown' if unsure.")
