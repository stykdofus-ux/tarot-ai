from flask import Flask, render_template, request, send_file, jsonify, url_for, session, redirect
import requests
import io
import os
import secrets
import random
import hashlib
import base64
from urllib.parse import urlencode

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

# --- CONFIGURATION ---
APP_KEY = "pk_B1ajqj2fxCArV7du"
APP_REDIRECT_URI = "https://oracle-mystique.up.railway.app/callback"
POLLINATIONS_AUTHORIZE_URL = "https://enter.pollinations.ai/authorize"
POLLINATIONS_TOKEN_URL = "https://enter.pollinations.ai/api/oauth/token"
IMAGE_API_URL = "https://gen.pollinations.ai/v1/images/generations"
TEXT_API_URL = "https://gen.pollinations.ai/v1/chat/completions"
DEFAULT_IMAGE_MODEL = "community/sharktide/inferenceport-ai-lightning-image-turbo"
DEFAULT_TEXT_MODEL = "qwen/qwen3-coder-30b-a3b-instruct"

# Tarot deck (78 cards: 22 Major Arcana + 56 Minor Arcana)
MAJOR_ARCANA = [
    {"name": "The Fool", "number": 0, "keywords": "beginnings, innocence, spontaneity"},
    {"name": "The Magician", "number": 1, "keywords": "willpower, skill, resourcefulness"},
    {"name": "The High Priestess", "number": 2, "keywords": "intuition, mystery, inner knowledge"},
    {"name": "The Empress", "number": 3, "keywords": "nurturing, abundance, fertility"},
    {"name": "The Emperor", "number": 4, "keywords": "authority, structure, stability"},
    {"name": "The Hierophant", "number": 5, "keywords": "tradition, wisdom, spiritual guidance"},
    {"name": "The Lovers", "number": 6, "keywords": "love, harmony, choices"},
    {"name": "The Chariot", "number": 7, "keywords": "willpower, determination, victory"},
    {"name": "Strength", "number": 8, "keywords": "courage, inner strength, compassion"},
    {"name": "The Hermit", "number": 9, "keywords": "introspection, solitude, wisdom"},
    {"name": "Wheel of Fortune", "number": 10, "keywords": "change, cycles, destiny"},
    {"name": "Justice", "number": 11, "keywords": "fairness, truth, balance"},
    {"name": "The Hanged Man", "number": 12, "keywords": "sacrifice, new perspective, surrender"},
    {"name": "Death", "number": 13, "keywords": "transformation, endings, rebirth"},
    {"name": "Temperance", "number": 14, "keywords": "balance, moderation, patience"},
    {"name": "The Devil", "number": 15, "keywords": "bondage, materialism, shadow self"},
    {"name": "The Tower", "number": 16, "keywords": "upheaval, revelation, awakening"},
    {"name": "The Star", "number": 17, "keywords": "hope, inspiration, serenity"},
    {"name": "The Moon", "number": 18, "keywords": "illusion, fear, subconscious"},
    {"name": "The Sun", "number": 19, "keywords": "joy, success, vitality"},
    {"name": "Judgement", "number": 20, "keywords": "rebirth, inner calling, absolution"},
    {"name": "The World", "number": 21, "keywords": "completion, accomplishment, wholeness"},
]

SUITS = ["Wands", "Cups", "Swords", "Pentacles"]
MINOR_ARCANA = []
for suit in SUITS:
    for i in range(1, 11):
        rank = {1: "Ace", 2: "Two", 3: "Three", 4: "Four", 5: "Five",
                6: "Six", 7: "Seven", 8: "Eight", 9: "Nine", 10: "Ten"}[i]
        MINOR_ARCANA.append({"name": f"{rank} of {suit}", "suit": suit, "number": i,
                            "keywords": f"{rank.lower()} {suit.lower()} energy"})
    MINOR_ARCANA.append({"name": f"Page of {suit}", "suit": suit, "number": 11,
                        "keywords": f"messenger, exploration, {suit.lower()} energy"})
    MINOR_ARCANA.append({"name": f"Knight of {suit}", "suit": suit, "number": 12,
                        "keywords": f"action, ambition, {suit.lower()} energy"})
    MINOR_ARCANA.append({"name": f"Queen of {suit}", "suit": suit, "number": 13,
                        "keywords": f"nurturing, mastery, {suit.lower()} energy"})
    MINOR_ARCANA.append({"name": f"King of {suit}", "suit": suit, "number": 14,
                        "keywords": f"authority, mastery, {suit.lower()} energy"})

ALL_CARDS = MAJOR_ARCANA + MINOR_ARCANA

# Interpretation prompts for AI
def get_tarot_interpretation_prompt(card, position, question):
    arcana_type = "Major Arcana" if card in MAJOR_ARCANA else "Minor Arcana"
    return f"""You are an expert tarot reader with deep knowledge of symbolism, archetypes, and spiritual guidance.

A querent asked: "{question}"

You drew the "{card['name']}" ({arcana_type}, card number {card.get('number', 'N/A')}) in the "{position}" position.

Keywords: {card.get('keywords', 'N/A')}

Provide a thoughtful, meaningful tarot reading interpretation:
1. Explain the core meaning of this card in this position
2. Connect it to the querent's question
3. Offer practical guidance and insight
4. Keep it mystical yet grounded and actionable

Respond in English. Keep it concise but profound (3-5 sentences)."""

def generate_code_verifier():
    return secrets.token_urlsafe(32)

def generate_code_challenge(verifier):
    sha256_hash = hashlib.sha256(verifier.encode('ascii')).digest()
    return base64.urlsafe_b64encode(sha256_hash).rstrip(b'=').decode('ascii')

@app.route('/')
def index():
    has_token = 'access_token' in session
    return render_template('index.html', logged_in=has_token)

@app.route('/connect')
def connect():
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)
    state = secrets.token_urlsafe(32)
    
    session['code_verifier'] = code_verifier
    session['oauth_state'] = state
    session['redirect_after_auth'] = url_for('index')
    
    auth_params = {
        'response_type': 'code',
        'client_id': APP_KEY,
        'redirect_uri': APP_REDIRECT_URI,
        'scope': 'usage',
        'state': state,
        'code_challenge': code_challenge,
        'code_challenge_method': 'S256'
    }
    
    auth_url = f"{POLLINATIONS_AUTHORIZE_URL}?{urlencode(auth_params)}"
    return redirect(auth_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    state = request.args.get('state')
    error = request.args.get('error')
    
    if not state or state != session.get('oauth_state'):
        return jsonify({"error": "Invalid state parameter"}), 400
    
    if error:
        return jsonify({"error": f"OAuth error: {error}"}), 400
    
    if not code:
        return jsonify({"error": "No authorization code received"}), 400
    
    code_verifier = session.get('code_verifier')
    if not code_verifier:
        return jsonify({"error": "PKCE code_verifier missing"}), 400
    
    try:
        token_res = requests.post(
            POLLINATIONS_TOKEN_URL,
            data={
                'grant_type': 'authorization_code',
                'code': code,
                'redirect_uri': APP_REDIRECT_URI,
                'client_id': APP_KEY,
                'code_verifier': code_verifier,
            },
            headers={'Accept': 'application/json'},
            timeout=30
        )
        
        if token_res.status_code != 200:
            return jsonify({
                "error": f"Token exchange failed: {token_res.status_code}",
                "details": token_res.text
            }), 400
        
        token_data = token_res.json()
        access_token = (
            token_data.get('access_token') or 
            token_data.get('token') or 
            token_data.get('id_token')
        )
        
        if not access_token:
            return jsonify({"error": "No access token in response", "response": token_data}), 400
        
        session['access_token'] = access_token
        session.pop('code_verifier', None)
        session.pop('oauth_state', None)
        
        return redirect(session.get('redirect_after_auth', url_for('index')))
        
    except Exception as e:
        return jsonify({"error": f"Connection error: {str(e)}"}, 500)

@app.route('/read', methods=['POST'])
def read():
    if 'access_token' not in session:
        return jsonify({"error": "Please connect your wallet first"}), 401
    
    data = request.get_json()
    question = data.get('question', '').strip()
    
    if not question:
        return jsonify({"error": "Please enter a question"}), 400
    
    access_token = session['access_token']
    
    try:
        # Draw 3 random cards (Past, Present, Future)
        drawn_cards = random.sample(ALL_CARDS, 3)
        positions = ["Past", "Present", "Future"]
        
        # Generate interpretations for each card
        interpretations = []
        for i, card in enumerate(drawn_cards):
            prompt = get_tarot_interpretation_prompt(card, positions[i], question)
            
            text_res = requests.post(
                TEXT_API_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": DEFAULT_TEXT_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 300,
                    "temperature": 0.8
                },
                timeout=60
            )
            
            if text_res.status_code == 200:
                text_data = text_res.json()
                interpretation = text_data.get("choices", [{}])[0].get("message", {}).get("content", "Lecture indisponible")
            else:
                interpretation = f"[Erreur de lecture: {text_res.status_code}]"
            
            interpretations.append({
                "card": card,
                "position": positions[i],
                "interpretation": interpretation
            })
        
        # Generate 3 tarot card images
        images = []
        for i, card in enumerate(drawn_cards):
            card_prompt = f"""Tarot card illustration of "{card['name']}". 
            {card.get('keywords', '')}. 
            Mystical, surreal, dark ambient atmosphere, glowing symbols, 
            celestial background, esoteric art style, rich colors, dramatic lighting, 
            vintage tarot aesthetic, highly detailed, 800x600"""
            
            img_res = requests.post(
                IMAGE_API_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": DEFAULT_IMAGE_MODEL,
                    "prompt": card_prompt,
                    "width": 800,
                    "height": 600,
                    "n": 1
                },
                timeout=120
            )
            
            if img_res.status_code == 200:
                if img_res.headers.get('Content-Type') == 'application/json':
                    img_data = img_res.json()
                    if "data" in img_data and "b64_json" in img_data["data"][0]:
                        images.append(base64.b64decode(img_data["data"][0]["b64_json"]))
                    else:
                        images.append(None)
                else:
                    images.append(img_res.content)
            else:
                images.append(None)
        
        return jsonify({
            "success": True,
            "reading": {
                "question": question,
                "draw_date": secrets.token_hex(8),  # pseudo-date for display
                "cards": [
                    {
                        "position": interpretations[i]["position"],
                        "card_name": interpretations[i]["card"]["name"],
                        "card_type": "Arcane Majeur" if interpretations[i]["card"] in MAJOR_ARCANA else "Arcane Mineur",
                        "keywords": interpretations[i]["card"].get("keywords", ""),
                        "interpretation": interpretations[i]["interpretation"],
                        "image": images[i] if images[i] else None
                    }
                    for i in range(3)
                ]
            }
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/disconnect')
def disconnect():
    session.pop('access_token', None)
    session.pop('code_verifier', None)
    session.pop('oauth_state', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
