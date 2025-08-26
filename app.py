from flask import Flask, render_template, request, jsonify
import spacy

app = Flask(__name__)
nlp = spacy.load("ru_core_news_lg")  # или en_core_web_lg

def extract_entities(text):
    doc = nlp(text)
    entities = [{"text": ent.text, "label": ent.label_} for ent in doc.ents]
    return entities

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/ner", methods=["POST"])
def ner():
    data = request.get_json()
    source_text = data.get("source", "")
    compare_text = data.get("compare", "")

    source_entities = extract_entities(source_text)
    compare_entities = extract_entities(compare_text)

    # Remove same NER
    unique_source = {ent["text"]: ent for ent in source_entities}.values()
    unique_compare = {ent["text"]: ent for ent in compare_entities}.values()

    #Matches
    matches = [ent for ent in unique_source if ent in unique_compare]

    #Nodes
    nodes_dict = {}
    for ent in list(unique_source) + list(unique_compare):
        nodes_dict[ent["text"]] = {"id": ent["text"], "group": ent["label"]}

    nodes = list(nodes_dict.values())
    links = [{"source": ent["text"], "target": ent["text"]} for ent in matches]

    return jsonify({
        "source_entities": list(unique_source),
        "compare_entities": list(unique_compare),
        "matches": matches,
        "graph": {"nodes": nodes, "links": links}
    })

if __name__ == "__main__":
    app.run(debug=True)
