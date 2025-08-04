import pdfplumber
import re
from keybert import KeyBERT
from sentence_transformers import SentenceTransformer
from langdetect import detect, LangDetectException
from collections import Counter
import itertools
import spacy
from Sastrawi.StopWordRemover.StopWordRemoverFactory import StopWordRemoverFactory

# === Load Model NLP Global ===
embedding_model = SentenceTransformer("paraphrase-multilingual-MPNet-base-v2")
kw_model = KeyBERT(embedding_model)

# === Load spaCy models ===
try:
    nlp_spacy = spacy.load("en_core_web_sm")
except Exception:
    nlp_spacy = None

try:
    nlp_multilang = spacy.load("xx_ent_wiki_sm")
except Exception:
    nlp_multilang = None

# === Stopword Bahasa Indonesia ===
stopword_factory = StopWordRemoverFactory()
indo_stopwords = set(stopword_factory.get_stop_words())

# === PDF to Text ===
def extract_text_from_pdf(file_path: str) -> str:
    try:
        with pdfplumber.open(file_path) as pdf:
            return ''.join(page.extract_text() or '' for page in pdf.pages)
    except Exception as e:
        print(f"[ERROR] PDF extract failed: {e}")
        return ""

# === Clean Text ===
def clean_text(text: str) -> str:
    text = text.replace('\x00', '')
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

# === Section Headers ===
SECTION_HEADERS = {
    "deskripsi": ["deskripsi diri", "profil", "profile", "summary", "tentang saya", "about me", "ringkasan", "objective"],
    "pendidikan": ["pendidikan", "education", "academic background"],
    "pengalaman": ["pengalaman kerja", "pengalaman", "experience", "work history", "employment"],
    "organisasi": ["organisasi", "aktivitas", "organization", "extracurricular", "volunteer"],
    "skill": ["skill", "keahlian", "kemampuan", "technical skill", "tools", "kompetensi", "expertise", "proficiency"]
}

# === Keyword Position ===
def find_all_keyword_positions(text: str, keywords: list[str]) -> list[int]:
    positions = []
    for k in keywords:
        for match in re.finditer(re.escape(k), text, flags=re.IGNORECASE):
            positions.append(match.start())
    return sorted(positions)

# === Extract Section ===
def extract_section(text: str, keywords: list[str], next_keywords: list[str]) -> str:
    start_positions = find_all_keyword_positions(text, keywords)
    end_positions = find_all_keyword_positions(text, next_keywords) if next_keywords else [len(text)]

    if not start_positions:
        return ""
    start = start_positions[0]
    end = next((e for e in end_positions if e > start), len(text))
    return text[start:end].strip()

# === Entity Extraction ===
def extract_entities(text: str, language: str) -> list[str]:
    if language == "en" and nlp_spacy:
        doc = nlp_spacy(text)
    elif language == "id" and nlp_multilang:
        doc = nlp_multilang(text)
    else:
        return []

    return [
        ent.text for ent in doc.ents
        if ent.label_ in ("ORG", "PRODUCT", "SKILL", "PERSON", "GPE", "WORK_OF_ART")
    ]

# === Keyword Extraction ===
def extract_keywords(text: str, language: str = "en", top_n: int = 25) -> list[str]:
    if not text or len(text.strip()) < 10:
        return []

    try:
        stop_lang = "english" if language == "en" else None
        candidates = kw_model.extract_keywords(
            text,
            keyphrase_ngram_range=(1, 3),
            stop_words=stop_lang,
            use_mmr=True,
            diversity=0.7,
            top_n=top_n * 3
        )
        keywords = [
            kw for kw, score in candidates
            if score > 0.35 and len(kw) > 2 and not kw.isdigit()
        ]

        # Filter stopwords Indonesia
        if language == "id":
            keywords = [
                k for k in keywords
                if all(word.lower() not in indo_stopwords for word in k.split())
            ]

        return list(dict.fromkeys(keywords[:top_n]))
    except Exception as e:
        print(f"[ERROR] Keyword extraction failed: {e}")
        return []

# === Boost Keywords ===
def boost_keywords(keywords: list[str], raw_text: str, min_required: int = 25) -> list[str]:
    if len(keywords) >= min_required:
        return keywords

    tokens = [w.lower() for w in re.findall(r'\b\w+\b', raw_text) if len(w) > 2]
    bigrams = zip(tokens, tokens[1:])
    trigrams = zip(tokens, tokens[1:], tokens[2:])
    phrases = [' '.join(p) for p in itertools.chain(bigrams, trigrams)]

    common_phrases = [p for p, c in Counter(phrases).most_common()
                      if p not in keywords and not p.isdigit()]

    boosted = keywords + common_phrases[:(min_required - len(keywords))]
    return list(dict.fromkeys(boosted))

# === Language Detection ===
def detect_language(text: str) -> str:
    try:
        return detect(text)
    except LangDetectException:
        return "unknown"

# === Final CV Processing ===
def process_cv(file_path: str) -> list[str]:
    raw_text = extract_text_from_pdf(file_path)
    cleaned_text = clean_text(raw_text)
    lang = detect_language(cleaned_text)

    deskripsi = extract_section(cleaned_text, SECTION_HEADERS["deskripsi"], SECTION_HEADERS["pendidikan"])
    pengalaman = extract_section(cleaned_text, SECTION_HEADERS["pengalaman"], SECTION_HEADERS["organisasi"])
    skill = extract_section(cleaned_text, SECTION_HEADERS["skill"], [])

    if not deskripsi:
        deskripsi = cleaned_text[:1000]

    keyword_text = " ".join([deskripsi, pengalaman, skill])
    keywords = extract_keywords(keyword_text, language=lang, top_n=25)

    entities = extract_entities(cleaned_text, language=lang)
    keywords += [e for e in entities if e.lower() not in [k.lower() for k in keywords]]

    final_keywords = boost_keywords(keywords, keyword_text, min_required=25)
    return list(dict.fromkeys(final_keywords))