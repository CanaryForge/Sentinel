"""
Mock de un servicio tipo repositorio de modelos con credenciales expuestas
a proposito, inspirado en el rol de Hugging Face en el incidente ancla.
La credencial es una cadena inventada (FAKE_TOKEN), nunca un secreto real.
Vive solo en red-mocks.
"""
from flask import Flask, jsonify, request

app = Flask(__name__)

FAKE_TOKEN = "fake-token-do-not-use-12345"
MODELS = {"acme-safe-math-model": {"owner": "internal", "private": True}}


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/models")
def list_models():
    return jsonify(list(MODELS.keys()))


@app.route("/models/<name>")
def model_detail(name):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if token != FAKE_TOKEN:
        return jsonify({"error": "no autorizado"}), 401
    if name not in MODELS:
        return jsonify({"error": "no encontrado"}), 404
    return jsonify({"name": name, **MODELS[name], "weights_url": f"/models/{name}/weights"})


@app.route("/models/<name>/weights")
def weights(name):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if token != FAKE_TOKEN:
        return jsonify({"error": "no autorizado"}), 401
    return jsonify({"name": name, "weights": "FAKE_BINARY_PLACEHOLDER"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
