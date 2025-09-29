
# Mottu Gestor — Protótipo IoT + Visão Computacional (YOLO)

## Serviços
- **Mosquitto** (MQTT)
- **Roboflow Inference (self-hosted)** em `http://localhost:9001` (CPU)
- **FastAPI** (ingestão, persistência SQLite, SSE, endpoints)
- **Simuladores** (RFID, Zona, Tamper)

## Subir o projeto
```
docker compose up -d --build
```
- Dashboard: http://localhost:8000/index.html
- Métricas: http://localhost:8000/metrics
- Relatório de localização: http://localhost:8000/report/location

## Detecção por imagem (Visão)
Enviar uma imagem para detecção:
```
*TODO*
```

## Tabelas SQLite
- `rfid_reads`, `zone_status`, `tamper_events`, `commands`, **`vision_events`**

## Casos de uso
- **Moto entrou/saiu**: derive por contagem/IDs de track (extensível com tracker).  
- **Moto em setor errado**: compare visão (zona da câmera) com alocação esperada.  
- **Violação**: combine `tamper=CUT/OPENED` com detecção de movimento.
