from mcp.server.fastmcp import FastMCP
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
import os
import httpx
import json
from typing import List, Dict, Any
import uvicorn
import threading
import time
import asyncio
import aiohttp
import requests

# Carrega as variáveis do arquivo .env
load_dotenv()

# Create an MCP server
mcp = FastMCP("RPG Gemini Server")

# Create FastAPI app for HTTP endpoints
app = FastAPI(title="RPG Gemini Hybrid Server")

# Global variable to store MCP tools results
mcp_results = {}

# Modelos Pydantic para validação de dados
class MessagePart(BaseModel):
    text: str

class Message(BaseModel):
    role: str
    parts: List[MessagePart]

class GeminiRequest(BaseModel):
    contents: List[Message]

# Função para detectar coordenadas dos destinos no mapa
def detect_map_coordinates():
    """Detecta automaticamente as coordenadas dos destinos no mapa"""
    map_layout = [
        "####################",
        "#P   1   W   2     #",
        "#                  #",
        "#    B   h   M   C #",
        "#                  #",
        "# 3   4       5    #",
        "#                  #",
        "#                  #",
        "# 5           6    #",
        "####################",
    ]
    
    destinations = {}
    
    for y, row in enumerate(map_layout):
        for x, tile in enumerate(row):
            if tile == 'h':  # Casa do jogador
                destinations["casa"] = {"x": x, "y": y}
            elif tile == 'W':  # Trabalho
                destinations["trabalho"] = {"x": x, "y": y}
            elif tile == 'M':  # Mercado
                destinations["mercado"] = {"x": x, "y": y}
            elif tile == 'B':  # Banco
                destinations["banco"] = {"x": x, "y": y}
            elif tile == 'C':  # Loja de Carros
                destinations["loja_carros"] = {"x": x, "y": y}
    
    return destinations

@mcp.tool()
def get_config() -> str:
    """Retorna as configurações necessárias para o frontend do jogo RPG.
    
    Returns:
        str: JSON com informações sobre disponibilidade da API Gemini
    """
    config = {
        "gemini_api_available": bool(os.getenv("GEMINI_API_KEY")),
        "message": "API Gemini configurada via backend"
    }
    return json.dumps(config)

@mcp.tool()
def get_destinations() -> str:
    """Retorna as coordenadas dos destinos detectadas automaticamente do mapa do jogo.
    
    Returns:
        str: JSON com as coordenadas dos destinos (casa, trabalho, mercado)
    """
    destinations = detect_map_coordinates()
    result = {
        "destinations": destinations,
        "message": "Coordenadas detectadas automaticamente do mapa"
    }
    return json.dumps(result)

@mcp.tool()
def generate_gemini_content(contents_json: str) -> str:
    """Executa uma chamada para a API Gemini para gerar conteúdo baseado nas mensagens fornecidas.
    
    Args:
        contents_json (str): JSON string contendo a lista de mensagens no formato [{"role": "user", "parts": [{"text": "mensagem"}]}]
    
    Returns:
        str: JSON com a resposta da API Gemini ou erro
    """
    try:
        # Verifica se a API key está configurada
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return json.dumps({
                "error": "GEMINI_API_KEY não configurada no arquivo .env",
                "status_code": 500
            })
        
        # Parse do JSON de entrada
        contents = json.loads(contents_json)
        
        # URL da API Gemini
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent?key={api_key}"
        
        # Prepara o payload
        payload = {"contents": contents}
        
        # Faz a chamada para a API Gemini usando requests síncronos
        import requests
        response = requests.post(
            api_url,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=30.0
        )
        
        if not response.ok:
            return json.dumps({
                "error": f"Erro na API Gemini: {response.status_code} - {response.text}",
                "status_code": response.status_code
            })
        
        result = response.json()
        
        # Extrai a resposta da API
        if "candidates" in result and len(result["candidates"]) > 0:
            ai_response = result["candidates"][0]["content"]["parts"][0]["text"]
            return json.dumps({"response": ai_response})
        else:
            return json.dumps({
                "error": "Resposta inválida da API Gemini",
                "status_code": 500
            })
            
    except json.JSONDecodeError:
        return json.dumps({
            "error": "JSON inválido fornecido",
            "status_code": 400
        })
    except requests.exceptions.Timeout:
        return json.dumps({
            "error": "Timeout na chamada da API Gemini",
            "status_code": 408
        })
    except requests.exceptions.RequestException as e:
        return json.dumps({
            "error": f"Erro de conexão com a API Gemini: {str(e)}",
            "status_code": 500
        })
    except Exception as e:
        return json.dumps({
            "error": f"Erro interno: {str(e)}",
            "status_code": 500
        })

@mcp.tool()
def move_player(destination: str) -> str:
    """Move o player para um destino específico no jogo RPG usando pathfinding.
    
    Args:
        destination (str): O destino para onde mover o player (casa, trabalho, mercado, banco)
    
    Returns:
        str: JSON com sucesso/erro, coordenadas do destino e status do player
    """
    try:
        # Detecta automaticamente as coordenadas dos destinos
        destinations = detect_map_coordinates()
        
        destination_lower = destination.lower()
        
        if destination_lower not in destinations:
            return json.dumps({
                "success": False,
                "message": f"Destino '{destination}' não encontrado. Destinos disponíveis: {', '.join(destinations.keys())}"
            })
        
        target_position = destinations[destination_lower]
        
        # Executa o movimento visual no frontend
        try:
            import asyncio
            import aiohttp
            
            async def trigger_frontend_movement():
                try:
                    async with aiohttp.ClientSession() as session:
                        # Chama o endpoint que executa JavaScript no frontend
                        await session.post('http://127.0.0.1:8080/api/execute-js', 
                                         json={'script': f'window.mcpMovePlayer("{destination_lower}")'})
                except:
                    pass  # Ignora erros de conexão
            
            # Executa de forma assíncrona sem bloquear
            try:
                loop = asyncio.get_event_loop()
                loop.create_task(trigger_frontend_movement())
            except:
                # Se não há loop, cria um novo
                asyncio.run(trigger_frontend_movement())
                
        except Exception as js_error:
            # Se falhar a execução do JavaScript, continua normalmente
            pass
        
        # Retorna sucesso e deixa o frontend usar findPath para calcular o caminho
        return json.dumps({
            "success": True,
            "message": f"Executando movimento para {destination_lower}...",
            "new_position": target_position,
            "frontend_triggered": True,
            "player_status": {
                "destination": destination_lower,
                "target_coordinates": target_position,
                "movement_type": "pathfinding",
                "status": "moving"
            }
        })
        
    except Exception as e:
        return json.dumps({
            "success": False,
            "message": f"Erro ao mover player: {str(e)}"
        })

@mcp.tool()
def get_player_status() -> str:
    """Get player status with stamina, pocket money, bank money, coordinates and current location from the running game"""
    import requests
    
    try:
        # Faz uma requisição para o endpoint de status
        response = requests.get('http://127.0.0.1:8080/api/get-player-status-live')
        if response.status_code == 200:
            return response.text
        else:
            # Fallback para o último status conhecido
            return json.dumps({
                "player_status": last_player_status
            }, ensure_ascii=False)
    except Exception as e:
        # Em caso de erro, retorna o último status conhecido
        return json.dumps({
            "player_status": last_player_status,
            "error": str(e)
        }, ensure_ascii=False)

@mcp.tool()
def pensamento(texto: str) -> str:
    """Exibe um pensamento do player em um balão de diálogo no jogo.
    
    Args:
        texto (str): O texto do pensamento que será exibido no balão
    
    Returns:
        str: JSON com sucesso/erro da operação
    """
    try:
        # JavaScript para criar um balão de pensamento para o player
        js_script = f"""
        if (typeof startDialogue === 'function' && typeof playerPosition !== 'undefined') {{
            // Cria um objeto temporário para representar o player como personagem
            const playerCharacter = {{
                name: 'Você',
                x: playerPosition.x,
                y: playerPosition.y
            }};
            
            // Cria a sequência de diálogo com o pensamento
            const thoughtSequence = [{{ text: '💭 {texto}' }}];
            
            // Inicia o diálogo como um pensamento temporizado
            startDialogue(thoughtSequence, playerCharacter, true, false, []);
            
            console.log('Pensamento exibido:', '{texto}');
        }} else {{
            console.error('Função startDialogue não encontrada ou playerPosition indefinido');
        }}
        """
        
        # Executa o JavaScript no frontend de forma assíncrona
        async def trigger_thought():
            try:
                async with aiohttp.ClientSession() as session:
                    await session.post('http://127.0.0.1:8080/api/execute-js', 
                                     json={'script': js_script})
            except:
                pass  # Ignora erros de conexão
        
        # Executa de forma assíncrona sem bloquear
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(trigger_thought())
        except:
            # Se não há loop, cria um novo
            asyncio.run(trigger_thought())
        
        return json.dumps({
            "success": True,
            "message": f"Pensamento '{texto}' exibido com sucesso",
            "texto": texto
        })
        
    except Exception as e:
        return json.dumps({
            "success": False,
            "message": f"Erro ao exibir pensamento: {str(e)}"
        })

# FastAPI endpoints that bridge to MCP tools
@app.get("/", response_class=HTMLResponse)
async def serve_game():
    """Serve the RPG game HTML"""
    try:
        with open("rpg_gemini.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Game file not found")

@app.get("/api/config")
async def get_config_endpoint():
    """HTTP endpoint that calls MCP get_config tool"""
    result = get_config()
    return json.loads(result)

@app.get("/api/destinations")
async def get_destinations_endpoint():
    """HTTP endpoint that calls MCP get_destinations tool"""
    result = get_destinations()
    return json.loads(result)

@app.post("/api/player/move")
async def move_player_endpoint(request: dict):
    """HTTP endpoint that calls MCP move_player tool"""
    destination = request.get("destination")
    if not destination:
        raise HTTPException(status_code=400, detail="Destination is required")
    
    result = move_player(destination)
    return json.loads(result)

@app.get("/api/player/status")
async def get_player_status_endpoint():
    """HTTP endpoint that calls MCP get_player_status tool"""
    result = get_player_status()
    return json.loads(result)

@app.post("/api/player/pensamento")
async def pensamento_endpoint(request: dict):
    """HTTP endpoint that calls MCP pensamento tool"""
    texto = request.get("texto")
    if not texto:
        raise HTTPException(status_code=400, detail="Texto is required")
    
    result = pensamento(texto)
    return json.loads(result)

@app.get("/api/player/real-status")
async def get_real_player_status():
    """HTTP endpoint to get real player status from JavaScript"""
    # Comando JavaScript para obter o status atual e retornar via fetch
    js_command = """
    if (typeof playerPosition !== 'undefined') {
        // Detecta a localização atual baseada nas coordenadas
        let currentLocation = 'desconhecido';
        const currentTile = mapGrid[playerPosition.y] ? mapGrid[playerPosition.y][playerPosition.x] : ' ';
        
        // Verifica se está em uma localização específica
        if (currentTile === 'H') {
            currentLocation = 'casa';
        } else if (currentTile === 'B') {
            currentLocation = 'banco';
        } else if (currentTile === 'M') {
            currentLocation = 'mercado';
        } else if (currentTile === 'W') {
            currentLocation = 'trabalho';
        } else if (currentTile === 'C') {
            currentLocation = 'loja_carros';
        } else {
            // Verifica se está próximo de alguma localização
            for (const [tile, location] of Object.entries(locations)) {
                if (location.x === playerPosition.x && location.y === playerPosition.y) {
                    switch(tile) {
                        case 'B': currentLocation = 'banco'; break;
                        case 'M': currentLocation = 'mercado'; break;
                        case 'W': currentLocation = 'trabalho'; break;
                        case 'C': currentLocation = 'loja_carros'; break;
                        default: currentLocation = 'area_livre';
                    }
                    break;
                }
            }
            if (currentLocation === 'desconhecido') {
                currentLocation = 'area_livre';
            }
        }
        
        const statusData = {
            stamina: playerPosition.stamina,
            dinheiro_bolso: playerPosition.moneyInPocket,
            dinheiro_banco: playerPosition.moneyInBank,
            coordenadas: { x: playerPosition.x, y: playerPosition.y },
            localizacao_atual: currentLocation,
            carros: playerPosition.carros || 0
        };
        
        // Envia o status para o servidor
        fetch('/api/player/update-status', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ player_status: statusData })
        }).catch(console.error);
    }
    """
    
    # Adiciona o comando à fila
    js_commands.append({
        "id": f"real_status_{int(time.time() * 1000)}",
        "script": js_command,
        "timestamp": time.time()
    })
    
    # Retorna o último status conhecido ou padrão
    return {
        "player_status": {
            "stamina": 100,
            "dinheiro_bolso": 0,
            "dinheiro_banco": 0,
            "coordenadas": {"x": 1, "y": 1},
            "localizacao_atual": "casa",
            "carros": 0,
            "nota": "Solicitando status real via JavaScript..."
        }
    }

# Variável global para armazenar o último status do player
last_player_status = {
    "stamina": 100,
    "dinheiro_bolso": 0,
    "dinheiro_banco": 0,
    "coordenadas": {"x": 1, "y": 1},
    "localizacao_atual": "casa",
    "carros": 0
}

@app.post("/api/player/update-status")
async def update_player_status(request: dict):
    """Endpoint para receber atualizações de status do JavaScript"""
    global last_player_status
    if "player_status" in request:
        last_player_status = request["player_status"]
    return {"success": True, "message": "Status atualizado"}

@app.get("/api/player/current-status")
async def get_current_player_status():
    """Retorna o último status conhecido do player"""
    return {"player_status": last_player_status}

@app.get("/api/player/request-status")
async def request_player_status():
    """Solicita o status atual do jogador via JavaScript e retorna quando disponível"""
    try:
        # JavaScript para chamar a função sendPlayerStatusToServer com logs detalhados
        js_code = """
        console.log('=== API REQUEST STATUS INICIADO ===');
        console.log('Verificando se sendPlayerStatusToServer existe:', typeof window.sendPlayerStatusToServer);
        console.log('Verificando playerPosition:', window.playerPosition);
        console.log('Verificando mapGrid:', window.mapGrid);
        
        if (typeof window.sendPlayerStatusToServer === 'function') {
            console.log('Chamando sendPlayerStatusToServer...');
            window.sendPlayerStatusToServer().then(result => {
                console.log('Status solicitado via API - Resultado:', result);
            }).catch(error => {
                console.error('Erro ao solicitar status via API:', error);
            });
        } else {
            console.error('Função sendPlayerStatusToServer não encontrada');
            console.log('Tentando chamar getPlayerStatus diretamente...');
            if (typeof window.getPlayerStatus === 'function') {
                const status = window.getPlayerStatus();
                console.log('Status obtido via getPlayerStatus:', status);
                
                // Envia manualmente para o servidor
                fetch('/api/player/update-status', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ player_status: status })
                }).then(response => response.json())
                  .then(data => console.log('Status enviado manualmente:', data))
                  .catch(error => console.error('Erro ao enviar status manualmente:', error));
            }
        }
        """
        
        # Adiciona o comando JavaScript à fila
        js_commands.append(js_code)
        
        # Aguarda mais tempo para o JavaScript executar
        await asyncio.sleep(1.0)
        
        # Retorna o último status conhecido
        return {"status": "success", "message": "Status solicitado com logs detalhados", "player_status": last_player_status}
        
    except Exception as e:
        return {"status": "error", "message": str(e), "player_status": last_player_status}

@app.get("/api/player/live-status")
async def get_live_player_status():
    """Força a captura do status atual do jogador via JavaScript"""
    try:
        # JavaScript para capturar status atual
        js_code = """
        (function() {
            try {
                let statusData = {
                    stamina: 100,
                    dinheiro_bolso: 0,
                    dinheiro_banco: 0,
                    coordenadas: { x: 1, y: 1 },
                    localizacao_atual: 'casa',
                    carros: 0
                };
                
                // Verifica se playerPosition está disponível
                if (typeof playerPosition !== 'undefined' && playerPosition) {
                    statusData.stamina = playerPosition.stamina || 100;
                    statusData.dinheiro_bolso = playerPosition.moneyInPocket || 0;
                    statusData.dinheiro_banco = playerPosition.moneyInBank || 0;
                    statusData.carros = playerPosition.carros || 0;
                    statusData.coordenadas = { 
                        x: playerPosition.x || 1, 
                        y: playerPosition.y || 1 
                    };
                    
                    // Detectar localização baseada no tile atual
                    if (typeof mapGrid !== 'undefined' && mapGrid[playerPosition.y]) {
                        const tile = mapGrid[playerPosition.y][playerPosition.x];
                        switch(tile) {
                            case 'H': statusData.localizacao_atual = 'casa'; break;
                            case 'B': statusData.localizacao_atual = 'banco'; break;
                            case 'M': statusData.localizacao_atual = 'mercado'; break;
                            case 'W': statusData.localizacao_atual = 'trabalho'; break;
                            case 'C': statusData.localizacao_atual = 'loja_carros'; break;
                            default: statusData.localizacao_atual = 'area_livre';
                        }
                    }
                }
                
                // Envia o status para o servidor
                fetch('/api/player/update-status', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ player_status: statusData })
                }).then(response => response.json())
                  .then(data => console.log('Status atualizado:', data))
                  .catch(error => console.error('Erro ao atualizar status:', error));
                  
                return statusData;
            } catch (error) {
                console.error('Erro ao capturar status:', error);
                return null;
            }
        })();
        """
        
        # Adiciona o comando JavaScript à fila
        js_commands.append(js_code)
        
        # Aguarda um pouco para o JavaScript executar
        await asyncio.sleep(0.5)
        
        # Retorna o último status conhecido
        return {"status": "success", "player_status": last_player_status}
        
    except Exception as e:
        return {"status": "error", "message": str(e), "player_status": last_player_status}

@app.get("/api/test-js")
async def test_javascript():
    """Endpoint para testar se o JavaScript está sendo executado"""
    # Comando JavaScript simples para teste
    test_command = """
    console.log('=== TESTE DE EXECUÇÃO JAVASCRIPT ===');
    console.log('Timestamp:', new Date().toISOString());
    console.log('playerPosition existe?', typeof playerPosition !== 'undefined');
    if (typeof playerPosition !== 'undefined') {
        console.log('playerPosition:', playerPosition);
    }
    console.log('mapGrid existe?', typeof mapGrid !== 'undefined');
    console.log('locations existe?', typeof locations !== 'undefined');
    
    // Tenta enviar um teste para o servidor
    fetch('/api/player/update-status', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
            player_status: {
                stamina: 999,
                dinheiro_bolso: 999,
                dinheiro_banco: 999,
                coordenadas: { x: 999, y: 999 },
                localizacao_atual: 'teste_js',
                carros: 999
            }
        })
    })
    .then(response => console.log('Teste enviado:', response.status))
    .catch(error => console.error('Erro no teste:', error));
    """
    
    # Adiciona o comando à fila
    js_commands.append({
        "id": f"test_js_{int(time.time() * 1000)}",
        "script": test_command,
        "timestamp": time.time()
    })
    
    return {"message": "Comando de teste JavaScript adicionado à fila", "check_console": "Verifique o console do navegador para logs"}

@app.post("/api/gemini/generate")
async def gemini_endpoint(request: dict):
    """HTTP endpoint that calls MCP generate_gemini_content tool"""
    contents = request.get("contents")
    if not contents:
        raise HTTPException(status_code=400, detail="Contents are required")
    
    contents_json = json.dumps(contents)
    result = generate_gemini_content(contents_json)
    return json.loads(result)

# Lista global para armazenar comandos JavaScript
js_commands = []
js_command_queue = []

@app.post("/api/execute-js")
async def execute_js_endpoint(request: dict):
    """Endpoint para executar JavaScript no frontend"""
    script = request.get("script")
    if not script:
        raise HTTPException(status_code=400, detail="script is required")
    
    # Adiciona o comando à fila
    js_command_queue.append({
        "script": script,
        "timestamp": time.time()
    })
    
    return {"success": True, "message": "Script adicionado à fila de execução"}

@app.get("/api/get-player-status-live")
async def get_player_status_live():
    """Endpoint que força a captura do status do jogador em tempo real via JavaScript"""
    try:
        # JavaScript que captura o status atual e o retorna via fetch
        js_code = """
        console.log('=== GET PLAYER STATUS LIVE INICIADO ===');
        
        // Função para capturar status atual
        function captureCurrentStatus() {
            let currentX = 1, currentY = 1, currentStamina = 100;
            let currentMoney = 0, currentBankMoney = 0, currentCars = 0;
            let currentLocation = 'casa';
            
            console.log('Verificando playerPosition:', window.playerPosition);
            console.log('Verificando playerPosition global:', typeof playerPosition !== 'undefined' ? playerPosition : 'undefined');
            
            // Tenta múltiplas formas de acessar a posição do jogador
            if (window.playerPosition) {
                currentX = window.playerPosition.x;
                currentY = window.playerPosition.y;
                currentStamina = window.playerPosition.stamina || 100;
                currentMoney = window.playerPosition.moneyInPocket || 0;
                currentBankMoney = window.playerPosition.moneyInBank || 0;
                currentCars = window.playerPosition.carros || 0;
                console.log('LIVE - Usando window.playerPosition:', window.playerPosition);
            } else if (typeof playerPosition !== 'undefined') {
                currentX = playerPosition.x;
                currentY = playerPosition.y;
                currentStamina = playerPosition.stamina || 100;
                currentMoney = playerPosition.moneyInPocket || 0;
                currentBankMoney = playerPosition.moneyInBank || 0;
                currentCars = playerPosition.carros || 0;
                console.log('LIVE - Usando playerPosition global:', playerPosition);
            } else {
                console.log('LIVE - playerPosition não encontrado, usando valores padrão');
            }
            
            // Detecta localização baseada no tile
            if (window.mapGrid && window.mapGrid[currentY] && window.mapGrid[currentY][currentX]) {
                const tile = window.mapGrid[currentY][currentX];
                console.log('LIVE - Tile detectado:', tile, 'na posição:', currentX, currentY);
                switch(tile) {
                    case 'H': currentLocation = 'casa'; break;
                    case 'B': currentLocation = 'banco'; break;
                    case 'M': currentLocation = 'mercado'; break;
                    case 'W': currentLocation = 'trabalho'; break;
                    case 'C': currentLocation = 'loja_carros'; break;
                    default: currentLocation = 'area_livre';
                }
            } else if (typeof mapGrid !== 'undefined' && mapGrid[currentY] && mapGrid[currentY][currentX]) {
                const tile = mapGrid[currentY][currentX];
                console.log('LIVE - Tile detectado via mapGrid global:', tile);
                switch(tile) {
                    case 'H': currentLocation = 'casa'; break;
                    case 'B': currentLocation = 'banco'; break;
                    case 'M': currentLocation = 'mercado'; break;
                    case 'W': currentLocation = 'trabalho'; break;
                    case 'C': currentLocation = 'loja_carros'; break;
                    default: currentLocation = 'area_livre';
                }
            }
            
            const statusData = {
                stamina: currentStamina,
                dinheiro_bolso: currentMoney,
                dinheiro_banco: currentBankMoney,
                coordenadas: { x: currentX, y: currentY },
                localizacao_atual: currentLocation,
                carros: currentCars,
                timestamp: new Date().toISOString()
            };
            
            console.log('LIVE - Status capturado:', statusData);
            return statusData;
        }
        
        // Captura o status e envia para o servidor
        const status = captureCurrentStatus();
        
        // Envia o status atualizado para o servidor
        fetch('/api/player/update-status', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ player_status: status })
        }).then(response => response.json())
          .then(data => {
              console.log('LIVE - Status enviado com sucesso:', data);
              // Marca que o status foi atualizado
              window.lastStatusUpdate = status;
          })
          .catch(error => console.error('LIVE - Erro ao enviar status:', error));
        """
        
        # Adiciona o comando JavaScript à fila
        js_command_queue.append({
            "script": js_code,
            "timestamp": time.time()
        })
        
        # Aguarda o JavaScript executar
        await asyncio.sleep(1.5)
        
        # Retorna o último status atualizado
        return {
            "status": "success", 
            "message": "Status capturado em tempo real", 
            "player_status": last_player_status,
            "timestamp": time.time()
        }
        
    except Exception as e:
        return {
            "status": "error", 
            "message": str(e), 
            "player_status": last_player_status
        }

@app.get("/api/js-commands")
async def get_js_commands():
    """Endpoint para o frontend buscar comandos JavaScript pendentes"""
    global js_command_queue
    
    # Remove comandos antigos (mais de 30 segundos)
    current_time = time.time()
    js_command_queue = [cmd for cmd in js_command_queue if current_time - cmd["timestamp"] < 30]
    
    # Retorna todos os comandos pendentes e limpa a fila
    commands = js_command_queue.copy()
    js_command_queue.clear()
    
    return {"commands": commands}

def run_fastapi():
    """Run FastAPI server in a separate thread"""
    uvicorn.run(app, host="127.0.0.1", port=8080)

def run_mcp():
    """Run MCP server in a separate thread"""
    mcp.run(transport="sse")

if __name__ == "__main__":
    print("Starting Hybrid Server (FastAPI + MCP)...")
    print("FastAPI: http://127.0.0.1:8080")
    print("MCP: SSE transport")
    
    # Start FastAPI in a separate thread
    fastapi_thread = threading.Thread(target=run_fastapi, daemon=True)
    fastapi_thread.start()
    
    # Run MCP in main thread
    run_mcp()