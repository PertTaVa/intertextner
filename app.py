from flask import Flask, render_template, request, jsonify
import spacy
import re
from collections import defaultdict
import inspect

# ФИКС ДЛЯ PYTHON 3.11: добавляем обратную совместимость
if not hasattr(inspect, 'getargspec'):
    inspect.getargspec = inspect.getfullargspec

# Пытаемся импортировать pymorphy3 (для Python 3.11+)
try:
    import pymorphy3
    PYTMORPHY_AVAILABLE = True
    morph = pymorphy3.MorphAnalyzer()
    print("✓ pymorphy3 загружен")
except ImportError:
    PYTMORPHY_AVAILABLE = False
    print("! pymorphy3 не установлен. Установите: pip install pymorphy3")
    morph = None

app = Flask(__name__)

# Загружаем модель spaCy
try:
    nlp = spacy.load("ru_core_news_lg")
    print("✓ Модель ru_core_news_lg загружена")
except:
    print("! Модель ru_core_news_lg не найдена. Установите: python -m spacy download ru_core_news_lg")
    nlp = spacy.load("ru_core_news_sm")  # возврат на маленькую модель


def normalize_russian(text, entity_type=None):
    """
    Нормализуем русский текст (приводит к именительному падежу)
    """
    if not PYTMORPHY_AVAILABLE or not morph:
        return text
    
    # Очищаем от лишних символов
    text = re.sub(r'[^\w\s-]', '', text).strip()
    if not text:
        return text
    
    try:
        parsed = morph.parse(text)[0]
        normal_form = parsed.normal_form
        
        # Для локаций и имён сохраняем заглавную букву
        if text and text[0].isupper():
            normal_form = normal_form.capitalize()
        
        return normal_form
    except:
        return text


def extract_entities(text, normalize=True):
    """
    Извлекает сущности из текста с опциональной нормализацией
    """
    doc = nlp(text)
    entities = []
    
    for ent in doc.ents:
        entity_text = ent.text
        if normalize:
            entity_text = normalize_russian(entity_text, ent.label_)
        
        entities.append({
            "text": entity_text,
            "original_text": ent.text,  # сохраняем оригинал для контекста
            "label": ent.label_,
            "start": ent.start_char,
            "end": ent.end_char,
            "context": text[max(0, ent.start_char-50):min(len(text), ent.end_char+50)] + "..."
        })
    
    return entities


def group_entities(entities):
    """
    Группирует сущности по тексту (после нормализации)
    """
    grouped = defaultdict(lambda: {
        "count": 0,
        "label": None,
        "original_texts": [],
        "contexts": []
    })
    
    for ent in entities:
        key = ent["text"]
        grouped[key]["count"] += 1
        grouped[key]["original_texts"].append(ent["original_text"])
        if ent["context"] and len(grouped[key]["contexts"]) < 3:
            grouped[key]["contexts"].append(ent["context"])
        if not grouped[key]["label"]:
            grouped[key]["label"] = ent["label"]
    
    # Преобразуем в список для удобства
    result = []
    for text, data in grouped.items():
        result.append({
            "text": text,
            "label": data["label"],
            "count": data["count"],
            "original_texts": list(set(data["original_texts"])),  # уникальные
            "contexts": data["contexts"]
        })
    
    # Сортируем по убыванию частоты
    result.sort(key=lambda x: x["count"], reverse=True)
    
    return result


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/ner", methods=["POST"])
def ner():
    data = request.get_json()
    source_text = data.get("source", "")
    compare_text = data.get("compare", "")
    
    # Извлекаем сущности с нормализацией
    source_entities_raw = extract_entities(source_text, normalize=True)
    compare_entities_raw = extract_entities(compare_text, normalize=True)
    
    # Группируем (объединяем одинаковые после нормализации)
    source_entities = group_entities(source_entities_raw)
    compare_entities = group_entities(compare_entities_raw)
    
    # Создаем множества для быстрого поиска
    source_dict = {ent["text"]: ent for ent in source_entities}
    compare_dict = {ent["text"]: ent for ent in compare_entities}
    
    # Находим совпадения (общие сущности)
    matches = []
    match_details = []
    
    all_texts = set(source_dict.keys()) | set(compare_dict.keys())
    
    for text in all_texts:
        in_source = text in source_dict
        in_compare = text in compare_dict
        
        if in_source and in_compare:
            # Сущность есть в обоих текстах
            source_ent = source_dict[text]
            compare_ent = compare_dict[text]
            
            matches.append(text)
            match_details.append({
                "text": text,
                "label": source_ent["label"],
                "source_count": source_ent["count"],
                "compare_count": compare_ent["count"],
                "total_count": source_ent["count"] + compare_ent["count"],
                "source_originals": source_ent["original_texts"],
                "compare_originals": compare_ent["original_texts"],
                "source_contexts": source_ent["contexts"],
                "compare_contexts": compare_ent["contexts"]
            })
    
    # Сортируем совпадения по убыванию общей частоты
    match_details.sort(key=lambda x: x["total_count"], reverse=True)
    
    # Подготовка данных для графа (nodes и links)
    nodes = []
    nodes_dict = {}
    
    # Добавляем узлы для текстов
    nodes_dict["SOURCE_TEXT"] = {"id": "SOURCE_TEXT", "group": "TEXT", "size": 10}
    nodes_dict["COMPARE_TEXT"] = {"id": "COMPARE_TEXT", "group": "TEXT", "size": 10}
    
    # Добавляем узлы для общих сущностей
    for ent in match_details:
        nodes_dict[ent["text"]] = {
            "id": ent["text"],
            "group": ent["label"],
            "size": 5 + min(ent["total_count"], 10)
        }
    
    nodes = list(nodes_dict.values())
    
    # Создаем связи
    links = []
    for ent in match_details:
        # Связь с исходным текстом
        links.append({
            "source": "SOURCE_TEXT",
            "target": ent["text"],
            "value": ent["source_count"]
        })
        # Связь с текстом сравнения
        links.append({
            "source": "COMPARE_TEXT",
            "target": ent["text"],
            "value": ent["compare_count"]
        })
    
    # Статистика
    stats = {
        "source_total": len(source_entities_raw),
        "source_unique": len(source_entities),
        "compare_total": len(compare_entities_raw),
        "compare_unique": len(compare_entities),
        "matches_count": len(matches)
    }
    
    return jsonify({
        "source_entities": source_entities,
        "compare_entities": compare_entities,
        "matches": matches,
        "match_details": match_details,
        "graph": {
            "nodes": nodes,
            "targets": ["SOURCE_TEXT", "COMPARE_TEXT"],
            "links": links
        },
        "stats": stats
    })


if __name__ == "__main__":
    app.run(debug=True)