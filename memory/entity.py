"""Simple entity extraction."""
import re


def extract_entities(text: str) -> dict:
    entities = {"people": [], "urls": [], "topics": [], "tags": []}
    url_pattern = re.compile(r"https?://[^\s,)]+")
    entities["urls"] = list(set(url_pattern.findall(text)))
    topic_words = [w for w in text.split() if w[0].isupper() and len(w) > 3]
    entities["topics"] = list(set(topic_words))
    return entities
