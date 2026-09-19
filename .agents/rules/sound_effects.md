# SOUND EFFECT ASSETS CONVENTION

All sound effect (SFX) audio files located in `assets/sounds/effect/` MUST strictly comply with the following rules:

## 1. File Naming Structure

Sound effect files must follow the pattern:
```
<Sound Name> - <Usage Description>.<ext>
```

- **`<Sound Name>`**: The auditory sound category or onomatopoeia, capitalized (e.g., `Ting`, `Boom`, `Cash`, `Bye Bye`, `Meow`, `Nope`, `Fart`, `Scratch`).
- **` - `**: A hyphen surrounded by single spaces (`[Space]-[Space]`). This delimiter is strictly required by `sound_effect_manager.py` to parse `<Sound Name>` and `<Usage Description>`.
- **`<Usage Description>`**: Concise English description explaining the intended scene purpose, dramatic mood, or highlight context (e.g., `Highlight Lucrative Salary And Bonus`, `Farewell To Old Job Or Outro`, `Awkward Failure Or Funny Outro`).
- **`<ext>`**: Supported audio format extensions (e.g., `.mp3`, `.wav`).

## 2. Uniqueness & Prefix Rules

- Sound name prefixes should be distinct across the library to prevent ambiguous tag generation.
- If multiple variations exist, specify the variation in the sound name or usage description clearly.

## 3. Integration with AI Prompt Generation

The system automatically scans `assets/sounds/effect/` and formats available sound effects into Gemini AI prompts:
- Each file conforming to `<Sound Name> - <Usage Description>.<ext>` produces:
  `- '<filename>' (Sound: '<Sound Name>' | Usage: <Usage Description>) -> Tag: [sound-effect:<filename>]`
- This ensures LLMs accurately match sound effects to script scenes and place `[sound-effect:<filename>]` tags at the end of sentences.
