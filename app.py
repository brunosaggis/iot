"""
IOT - Inteligência Operacional Territorial
Backend Flask para otimização de rotas
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import pandas as pd
import requests
import os
from math import radians, cos, sin, sqrt, atan2
from io import BytesIO
import uuid

app = Flask(__name__, static_folder='static')
CORS(app)

API_KEY = "AIzaSyCN5jhZqcd8qs1cCdXjTlJS0wabjUmeTjA"
geocode_cache = {}

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/api/health')
def health():
    return jsonify({'status': 'ok'})

def geocode_address(endereco, bairro, cidade="Guarujá", estado="SP"):
    """Geocodifica um endereço usando Google Maps API"""
    full_address = f"{endereco}, {bairro}, {cidade} - {estado}, Brasil"
    
    if full_address in geocode_cache:
        cached = geocode_cache[full_address]
        return cached['lat'], cached['lng']
    
    try:
        url = f"https://maps.googleapis.com/maps/api/geocode/json?address={requests.utils.quote(full_address)}&key={API_KEY}"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data['status'] == 'OK' and len(data['results']) > 0:
            location = data['results'][0]['geometry']['location']
            geocode_cache[full_address] = {'lat': location['lat'], 'lng': location['lng']}
            return location['lat'], location['lng']
    except Exception as e:
        print(f"Erro geocoding: {e}")
    
    return None, None

def haversine(lat1, lng1, lat2, lng2):
    """Calcula distância entre dois pontos em km"""
    R = 6371
    lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlng/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    return R * c

def nearest_neighbor(pontos):
    """Algoritmo do vizinho mais próximo para otimização de rota"""
    if not pontos:
        return []
    
    pontos_validos = [p for p in pontos if p.get('lat') and p.get('lng')]
    if not pontos_validos:
        return pontos
    
    rota = [pontos_validos[0]]
    restantes = pontos_validos[1:]
    
    while restantes:
        atual = rota[-1]
        mais_proximo = min(restantes, key=lambda p: haversine(
            atual['lat'], atual['lng'], p['lat'], p['lng']
        ))
        rota.append(mais_proximo)
        restantes.remove(mais_proximo)
    
    return rota

@app.route('/api/processar', methods=['POST'])
def processar_arquivo():
    """Processa arquivo CSV/Excel e retorna registros"""
    if 'file' not in request.files:
        return jsonify({'error': 'Nenhum arquivo enviado'}), 400
    
    file = request.files['file']
    
    try:
        if file.filename.endswith('.csv'):
            content = file.read()
            try:
                df = pd.read_csv(BytesIO(content), encoding='utf-8')
            except:
                try:
                    df = pd.read_csv(BytesIO(content), encoding='latin-1')
                except:
                    df = pd.read_csv(BytesIO(content), encoding='utf-8', sep=';')
        else:
            df = pd.read_excel(BytesIO(file.read()))
        
        df.columns = [c.lower().strip().replace(' ', '_') for c in df.columns]
        
        registros = []
        for idx, row in df.iterrows():
            numero_os = str(row.get('numero_os', row.get('os', row.get('numero', idx + 1))))
            if numero_os == 'nan':
                numero_os = str(idx + 1)
            
            endereco = str(row.get('endereco', row.get('endereço', '')))
            if endereco == 'nan':
                endereco = ''
            
            bairro = str(row.get('bairro', ''))
            if bairro == 'nan':
                bairro = ''
            
            registros.append({
                'id': str(uuid.uuid4()),
                'numero_os': numero_os,
                'endereco': endereco,
                'bairro': bairro,
                'lat': None,
                'lng': None
            })
        
        return jsonify({
            'success': True,
            'total': len(registros),
            'registros': registros
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/geocode-lote', methods=['POST'])
def geocode_lote():
    """Geocodifica um lote de registros"""
    data = request.json
    registros = data.get('registros', [])
    
    resultados = []
    for reg in registros:
        lat, lng = geocode_address(reg.get('endereco', ''), reg.get('bairro', ''))
        resultados.append({
            'id': reg['id'],
            'lat': lat,
            'lng': lng
        })
    
    return jsonify({'resultados': resultados})

@app.route('/api/otimizar', methods=['POST'])
def otimizar():
    """Otimiza a rota usando algoritmo do vizinho mais próximo"""
    data = request.json
    pontos = data.get('pontos', [])
    
    pontos_validos = [p for p in pontos if p.get('lat') and p.get('lng')]
    
    if not pontos_validos:
        return jsonify({'error': 'Nenhum ponto com coordenadas válidas'}), 400
    
    rota_otimizada = nearest_neighbor(pontos_validos)
    
    distancia_total = 0
    for i in range(len(rota_otimizada) - 1):
        p1, p2 = rota_otimizada[i], rota_otimizada[i + 1]
        distancia_total += haversine(p1['lat'], p1['lng'], p2['lat'], p2['lng'])
    
    bairros = set(p.get('bairro', '') for p in rota_otimizada if p.get('bairro'))
    
    resultado = []
    for idx, ponto in enumerate(rota_otimizada):
        resultado.append({
            'seq': idx + 1,
            'id': ponto['id'],
            'numero_os': ponto['numero_os'],
            'endereco': ponto['endereco'],
            'bairro': ponto['bairro'],
            'lat': ponto['lat'],
            'lng': ponto['lng']
        })
    
    return jsonify({
        'success': True,
        'rota': resultado,
        'stats': {
            'total': len(resultado),
            'bairros': len(bairros),
            'distancia': round(distancia_total, 1)
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
