import os
import gc
import time
import json
import re
import threading
import http.server
import socketserver
import hashlib
import base64
import requests
from datetime import datetime, timezone, timedelta

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

os.chdir(os.path.dirname(os.path.abspath(__file__)))
comando_f1_pendente = None

# ==============================================================================
# CONFIGURAÇÃO DO LINK DA PARTIDA E TORNEIO
# ==============================================================================
URL_DO_JOGO = ""

# ==============================================================================
# SISTEMA DE CACHE LOCAL VIA CHROME
# ==============================================================================
CACHE_IMG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache_img")
os.makedirs(CACHE_IMG_DIR, exist_ok=True)

def salvar_base64_disco(caminho, b64_str):
    try:
        if "," in b64_str:
            b64_str = b64_str.split(",", 1)[1]
        bytes_img = base64.b64decode(b64_str)
        if len(bytes_img) > 50:
            with open(caminho, "wb") as f:
                f.write(bytes_img)
            return True
    except Exception:
        pass
    return False

def cachear_todas_imagens(driver_instance, dados_lista):
    if not dados_lista or not isinstance(dados_lista, list):
        return dados_lista

    urls_para_descarregar = set()
    for item in dados_lista:
        if not isinstance(item, dict): 
            continue
        
        # Cache de imagens da F1 (Fotos de Pilotos e Logos de Equipes)
        if item.get("esporte") == "f1":
            for p in item.get("classificacaoF1", []):
                if isinstance(p, dict):
                    if p.get("foto"): urls_para_descarregar.add(p["foto"])
                    if p.get("logoEquipe"): urls_para_descarregar.add(p["logoEquipe"])

        for k in ["logoCasa", "logoFora"]:
            if item.get(k): 
                urls_para_descarregar.add(item[k])
                
        # Logos da tabela simples
        for t in item.get("tabela", []):
            if isinstance(t, dict) and t.get("logo"):
                urls_para_descarregar.add(t["logo"])

        # Logos de todos os grupos
        for grp in item.get("grupos", []):
            if isinstance(grp, dict):
                for t in grp.get("times", []):
                    if isinstance(t, dict) and t.get("logo"):
                        urls_para_descarregar.add(t["logo"])

        # Logos dos confrontos de mata-mata
        for fase in item.get("matamata", []):
            if isinstance(fase, dict):
                for m in fase.get("jogos", []):
                    if isinstance(m, dict):
                        if m.get("logo1"): urls_para_descarregar.add(m["logo1"])
                        if m.get("logo2"): urls_para_descarregar.add(m["logo2"])

        for esc in [item.get("escalacaoCasa", []), item.get("escalacaoFora", [])]:
            if isinstance(esc, list):
                for p in esc:
                    if isinstance(p, dict) and p.get("foto"):
                        urls_para_descarregar.add(p["foto"])

        for ldr in item.get("lideres_nfl", []):
            if isinstance(ldr, dict):
                for lado in ["away", "home"]:
                    p = ldr.get(lado)
                    if isinstance(p, dict) and p.get("foto"):
                        urls_para_descarregar.add(p["foto"])

        for oj in item.get("outros_jogos", []):
            if isinstance(oj, dict):
                for k in ["logo1", "logo2"]:
                    if oj.get(k): 
                        urls_para_descarregar.add(oj[k])

    mapa_cache = {}
    urls_pendentes = []

    for u in urls_para_descarregar:
        if not u or not isinstance(u, str) or not u.startswith("http"):
            continue
        
        extensao = ".png" if ".png" in u.lower() else (".webp" if ".webp" in u.lower() else ".jpg")
        nome_arquivo = hashlib.md5(u.encode("utf-8")).hexdigest() + extensao
        caminho_disco = os.path.join(CACHE_IMG_DIR, nome_arquivo)
        caminho_relativo = f"cache_img/{nome_arquivo}"

        if os.path.exists(caminho_disco) and os.path.getsize(caminho_disco) > 50:
            mapa_cache[u] = caminho_relativo
        else:
            urls_pendentes.append(u)

    if urls_pendentes and driver_instance:
        script_fetch_chrome = """
        const done = arguments[arguments.length - 1];
        const urls = arguments[0];

        async function obterImagem(url) {
            if (!url || !url.startsWith('http')) return { url: url, data: null };
            try {
                let resp = await fetch(url);
                if (!resp.ok) return { url: url, data: null };
                const blob = await resp.blob();
                return new Promise(resolve => {
                    const reader = new FileReader();
                    reader.onloadend = () => resolve({ url: url, data: reader.result });
                    reader.onerror = () => resolve({ url: url, data: null });
                    reader.readAsDataURL(blob);
                });
            } catch(e) {
                return { url: url, data: null };
            }
        }

        Promise.all(urls.map(u => obterImagem(u)))
            .then(res => done(res))
            .catch(() => done([]));
        """
        try:
            resultados = driver_instance.execute_async_script(script_fetch_chrome, urls_pendentes)
            novas_salvas = 0
            if resultados and isinstance(resultados, list):
                for item in resultados:
                    u = item.get("url")
                    b64 = item.get("data")
                    if u and b64 and isinstance(b64, str) and b64.startswith("data:image"):
                        extensao = ".png" if ".png" in u.lower() else (".webp" if ".webp" in u.lower() else ".jpg")
                        nome_arquivo = hashlib.md5(u.encode("utf-8")).hexdigest() + extensao
                        caminho_disco = os.path.join(CACHE_IMG_DIR, nome_arquivo)
                        caminho_relativo = f"cache_img/{nome_arquivo}"
                        if salvar_base64_disco(caminho_disco, b64):
                            mapa_cache[u] = caminho_relativo
                            novas_salvas += 1
            if novas_salvas > 0:
                print(f"[CACHE] {novas_salvas} novas imagens salvas com sucesso em 'cache_img/'!")
        except Exception:
            pass

    for item in dados_lista:
        if not isinstance(item, dict): 
            continue
        
        if item.get("esporte") == "f1":
            for p in item.get("classificacaoF1", []):
                if isinstance(p, dict):
                    if p.get("foto") in mapa_cache: p["foto"] = mapa_cache[p["foto"]]
                    if p.get("logoEquipe") in mapa_cache: p["logoEquipe"] = mapa_cache[p["logoEquipe"]]

        for k in ["logoCasa", "logoFora"]:
            if item.get(k) in mapa_cache:
                item[k] = mapa_cache[item[k]]
                
        for t in item.get("tabela", []):
            if isinstance(t, dict) and t.get("logo") in mapa_cache:
                t["logo"] = mapa_cache[t["logo"]]

        for grp in item.get("grupos", []):
            if isinstance(grp, dict):
                for t in grp.get("times", []):
                    if isinstance(t, dict) and t.get("logo") in mapa_cache:
                        t["logo"] = mapa_cache[t["logo"]]

        for fase in item.get("matamata", []):
            if isinstance(fase, dict):
                for m in fase.get("jogos", []):
                    if isinstance(m, dict):
                        if m.get("logo1") in mapa_cache: m["logo1"] = mapa_cache[m["logo1"]]
                        if m.get("logo2") in mapa_cache: m["logo2"] = mapa_cache[m["logo2"]]

        for esc in [item.get("escalacaoCasa", []), item.get("escalacaoFora", [])]:
            if isinstance(esc, list):
                for p in esc:
                    if isinstance(p, dict) and p.get("foto") in mapa_cache:
                        p["foto"] = mapa_cache[p["foto"]]

        for ldr in item.get("lideres_nfl", []):
            if isinstance(ldr, dict):
                for lado in ["away", "home"]:
                    p = ldr.get(lado)
                    if isinstance(p, dict) and p.get("foto") in mapa_cache:
                        p["foto"] = mapa_cache[p["foto"]]

        for oj in item.get("outros_jogos", []):
            if isinstance(oj, dict):
                for k in ["logo1", "logo2"]:
                    if oj.get(k) in mapa_cache:
                        oj[k] = mapa_cache[oj[k]]

    return dados_lista

# ==============================================================================
# 1. SERVIDOR HTTP AUTOMÁTICO (Porta 8000)
# ==============================================================================
class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args): pass
    def do_POST(self):
        global comando_f1_pendente
        if self.path.startswith("/trocar_sessao_f1"):
            tamanho = int(self.headers.get('Content-Length', 0))
            corpo = self.rfile.read(tamanho).decode('utf-8')
            comando_f1_pendente = corpo.strip()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        else:
            self.send_response(404)
            self.end_headers()
            
class QuietServer(socketserver.TCPServer):
    def handle_error(self, request, client_address): pass

def iniciar_servidor():
    PORTA = 8000
    try:
        with QuietServer(("", PORTA), QuietHandler) as httpd:
            httpd.serve_forever()
    except Exception: pass

threading.Thread(target=iniciar_servidor, daemon=True).start()

# ==============================================================================
# 2. CONEXÃO COM O CHROME
# ==============================================================================
print("=" * 60)
print("  SOFASCORE & ESPN OVERLAY PRO - INICIALIZAÇÃO DIRETA  ")
print("=" * 60)
print("-> Servidor OBS ativo em: http://localhost:8000/placar.html\n")

chrome_options = Options()
chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9333")

driver = None
for tentativa in range(1, 6):
    try:
        print(f"A tentar ligar ao Chrome (tentativa {tentativa}/5)...")
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        print("Ligado com sucesso à janela do Chrome!")
        break
    except Exception as e:
        print(f"   -> Falha na tentativa {tentativa}: {e}")
        time.sleep(2)

if not driver:
    print("\n[ERRO CRÍTICO] Não foi possível ligar ao Chrome na porta 9333.")
    print("Certifique-se de que o INICIAR_PLACAR.bat foi executado para abrir o navegador.")
    time.sleep(10)
    exit()

driver.set_script_timeout(10)

if URL_DO_JOGO.strip():
    driver.get(URL_DO_JOGO.strip())
    time.sleep(3)
else:
    url_atual = driver.current_url.lower()
    if "sofascore" not in url_atual and "espn" not in url_atual and "formula1" not in url_atual:
        print("Aguardando que abra a página do jogo no Chrome...")
        while "sofascore" not in driver.current_url.lower() and "espn" not in driver.current_url.lower() and "formula1" not in driver.current_url.lower():
            time.sleep(1)

try:
    driver.execute_script("window.scrollTo(0, 450);")
except Exception:
    pass

ultimo_tempo_valido = "Em andamento"
f1_cache_dados = None
f1_ultima_busca = 0
f1_url_cache = ""

# ==============================================================================
# 3. EXTRAÇÃO DE DADOS DA NFL VIA API DA ESPN
# ==============================================================================
posicoes_iniciais_times = {}
def extrair_dados_espn_nfl():
    try:
        url_atual = driver.current_url
        m_id = re.search(r'(?:gameId|jogoId|event)[=/:](\d+)', url_atual, re.IGNORECASE)
        if not m_id:
            m_id = re.search(r'/nfl/(?:game|boxscore|partida|matchup)[^/]*?/(\d{7,11})', url_atual, re.IGNORECASE)
        if not m_id:
            m_id = re.search(r'(\d{8,11})', url_atual)
            
        game_id = m_id.group(1) if m_id else ""

        script_extracao = """
        const done = arguments[arguments.length - 1];
        let gId = arguments[0];
        async function obterDadosNFL() {
            if (!gId) { try { gId = window.__espnfitt__?.page?.content?.gamepackage?.gmStrp?.gid || ""; } catch(e) {} }
            if (!gId) return null;
            try {
                let rCdn = await fetch(`https://cdn.espn.com/core/nfl/game?xhr=1&gameId=${gId}&t=${Date.now()}`, { cache: 'no-store' });
                if (rCdn.ok) {
                    let jCdn = await rCdn.json();
                    let gp = jCdn.gamepackage || (jCdn.gmStrp ? jCdn : null);
                    if (gp && gp.gmLdrs && gp.gmLdrs.ldrs && gp.gmLdrs.ldrs.length > 0) {
                        return { tipo: 'cdn', data: gp };
                    }
                }
            } catch(e) {}
            try {
                let r = await fetch(`https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event=${gId}&t=${Date.now()}`, { cache: 'no-store' });
                if (r.ok) {
                    let j = await r.json();
                    if (j && j.header) return { tipo: 'summary', data: j };
                }
            } catch(e) {}
            return null;
        }
        obterDadosNFL().then(res => done(res)).catch(() => done(null));
        """
        
        resp = driver.execute_async_script(script_extracao, game_id)
        if not resp or not resp.get("data"): return None
        tipo = resp.get("tipo")
        data = resp.get("data")
        trans_cat = {
            "passingyards": "Jds/Passe", "passingleader": "Jds/Passe", "passing": "Jds/Passe",
            "rushingyards": "Jds/corrida", "rushingleader": "Jds/corrida", "rushing": "Jds/corrida",
            "receivingyards": "Jds recebidas", "receivingleader": "Jds recebidas", "receiving": "Jds recebidas",
            "sacks": "Sacks", "sack": "Sacks", "totaltackles": "Tackles", "tackles": "Tackles", "interceptions": "Interceptações"
        }

        def separar_stat_e_detalhe(cat_chave, texto_bruto):
            txt = str(texto_bruto or "").strip()
            cat = cat_chave.lower()
            if not txt: return "-", ""
            if "pass" in cat:
                m = re.search(r'(\d+)\s*YDS', txt, re.IGNORECASE)
                if m:
                    stat = m.group(1)
                    detalhe = re.sub(r',?\s*\d+\s*YDS,?', '', txt, flags=re.IGNORECASE).strip(', ')
                    return stat, detalhe
            elif "rush" in cat:
                m = re.match(r'(\d+)\s*CAR,\s*(.*)', txt, re.IGNORECASE)
                if m: return m.group(1), m.group(2).replace("YDS", "JDS")
            elif "rec" in cat:
                m = re.match(r'(\d+)\s*REC,\s*(.*)', txt, re.IGNORECASE)
                if m: return m.group(1), m.group(2).replace("YDS", "JDS")
            elif "tackle" in cat:
                m = re.match(r'(\d+)(?:,\s*(.*))?', txt)
                if m: return m.group(1), m.group(2) or ""
            elif "sack" in cat:
                try:
                    f = float(txt)
                    return (str(int(f)) if f.is_integer() else str(f)), ""
                except Exception: pass
            return txt, ""

        if tipo == 'cdn':
            gmStrp = data.get('gmStrp', {})
            gmLdrs = data.get('gmLdrs', {})
            tms = gmStrp.get('tms', [])
            away_team = tms[0] if len(tms) > 0 else {}
            home_team = tms[1] if len(tms) > 1 else {}
            time_fora = away_team.get('shortDisplayName') or away_team.get('displayName') or away_team.get('abbrev', 'Fora')
            logo_fora = away_team.get('logo', '')
            abbrev_fora = away_team.get('abbrev', '')
            time_casa = home_team.get('shortDisplayName') or home_team.get('displayName') or home_team.get('abbrev', 'Casa')
            logo_casa = home_team.get('logo', '')
            abbrev_casa = home_team.get('abbrev', '')
            status = gmStrp.get('status', {})
            state = status.get('state', 'in')
            tempo_det = status.get('det', '')
            tempo_desc = status.get('desc', '')

            if state == 'pre':
                placar_fora, placar_casa = "-", "-"
                tempo = f"{tempo_det} • {tempo_desc}" if (tempo_det and tempo_desc and tempo_desc != tempo_det) else (tempo_det or tempo_desc or "EM BREVE")
            elif state == 'post':
                placar_fora = str(away_team.get('score', '-'))
                placar_casa = str(home_team.get('score', '-'))
                tempo = "FINALIZADO"
            else:
                placar_fora = str(away_team.get('score', '0'))
                placar_casa = str(home_team.get('score', '0'))
                tempo = tempo_det or tempo_desc or "AO VIVO"

            titulo_raw = gmLdrs.get('title', 'Líderes do Jogo')
            titulo_dest = "LÍDERES DA TEMPORADA" if ('temporada' in titulo_raw.lower() or 'season' in titulo_raw.lower() or state == 'pre') else "LÍDERES DO JOGO"

            lideres_formatados = []
            for ldr in gmLdrs.get('ldrs', []):
                name_key = ldr.get('name', '').lower()
                cat_label = trans_cat.get(name_key) or ldr.get('label', '')
                p_away = ldr.get('players', {}).get('away')
                p_home = ldr.get('players', {}).get('home')
                def extrair_p(p):
                    if not p or not p.get('nameShort'): return None
                    foto = p.get('headshotImg', '')
                    if 'nophoto' in foto: foto = ''
                    return {
                        "nome": p.get('nameShort', ''), "posicao": p.get('position', ''),
                        "detalhe": p.get('stats', ''), "stat": str(p.get('primaryStatValue', '-')), "foto": foto
                    }
                lideres_formatados.append({"categoria": cat_label, "away": extrair_p(p_away), "home": extrair_p(p_home)})

        else:
            header = data.get('header', {})
            comps = header.get('competitions', [{}])[0]
            competitors = comps.get('competitors', [])
            away_team, home_team = {}, {}
            for c in competitors:
                if c.get('homeAway') == 'away': away_team = c
                elif c.get('homeAway') == 'home': home_team = c

            t_away = away_team.get('team', {})
            t_home = home_team.get('team', {})
            time_fora = t_away.get('shortDisplayName') or t_away.get('displayName') or t_away.get('abbreviation', 'Fora')
            logo_fora = (t_away.get('logos') or [{}])[0].get('href', '') if t_away.get('logos') else t_away.get('logo', '')
            abbrev_fora = t_away.get('abbreviation', '')
            id_fora = str(t_away.get('id') or away_team.get('id', ''))
            placar_fora = str(away_team.get('score', '0'))
            time_casa = t_home.get('shortDisplayName') or t_home.get('displayName') or t_home.get('abbreviation', 'Casa')
            logo_casa = (t_home.get('logos') or [{}])[0].get('href', '') if t_home.get('logos') else t_home.get('logo', '')
            abbrev_casa = t_home.get('abbreviation', '')
            id_casa = str(t_home.get('id') or home_team.get('id', ''))
            placar_casa = str(home_team.get('score', '0'))
            st_obj = comps.get('status', {})
            st_type = st_obj.get('type', {})
            state = st_type.get('state', 'in')
            st_name = st_type.get('name', '').lower()
            tempo_det = st_type.get('detail', '')
            tempo_desc = st_type.get('description', '')
            display_clock = st_obj.get('displayClock', '')
            period = st_obj.get('period', 0)

            if state == 'pre':
                placar_fora, placar_casa = "-", "-"
                data_iso = comps.get('date', '')
                if data_iso:
                    try:
                        fuso_br = timezone(timedelta(hours=-3))
                        dt = datetime.fromisoformat(data_iso.replace("Z", "+00:00")).astimezone(fuso_br)
                        dias_semana = ["SEG", "TER", "QUA", "QUI", "SEX", "SÁB", "DOM"]
                        dia_sem = dias_semana[dt.weekday()]
                        tempo = f"{dia_sem}, {dt.strftime('%d/%m')} • {dt.strftime('%H:%M')}"
                    except Exception:
                        tempo = tempo_det or tempo_desc or "EM BREVE"
                else:
                    tempo = tempo_det or tempo_desc or "EM BREVE"
            elif state == 'post' or 'final' in st_name or 'final' in tempo_desc.lower() or 'final' in tempo_det.lower():
                tempo = "FINALIZADO"
                placar_fora = str(away_team.get('score', '-'))
                placar_casa = str(home_team.get('score', '-'))
            else:
                if 'halftime' in st_name or 'halftime' in tempo_desc.lower() or 'halftime' in tempo_det.lower() or 'intervalo' in tempo_det.lower():
                    tempo = "INTERVALO"
                elif 'end of' in tempo_desc.lower() or 'end_of' in st_name or (display_clock == "0:00" and period in [1, 3]):
                    tempo = f"FIM DO {period}º QUARTO"
                else:
                    periodo_txt = f"{period}º QUARTO" if 1 <= period <= 4 else ("OVERTIME" if period > 4 else "AO VIVO")
                    tempo = f"{display_clock} - {periodo_txt}" if display_clock else (tempo_det or tempo_desc or periodo_txt)

            titulo_dest = "LÍDERES DA TEMPORADA" if state == 'pre' else "LÍDERES DO JOGO"

            def extrair_atleta(entry, cat_nome):
                if not entry: return None
                ath = entry.get('athlete', {})
                if not ath: return None
                foto = ""
                if isinstance(ath.get('headshot'), dict): foto = ath.get('headshot', {}).get('href', '')
                elif isinstance(ath.get('headshot'), str): foto = ath.get('headshot', '')
                pos = ath.get('position', {})
                pos_str = pos.get('abbreviation', '') if isinstance(pos, dict) else str(pos or '')
                raw_val = str(entry.get('displayValue', '-'))
                st_val, det_val = separar_stat_e_detalhe(cat_nome, raw_val)
                return { "nome": ath.get('shortName') or ath.get('displayName', ''), "posicao": pos_str, "detalhe": det_val, "stat": st_val, "foto": foto }

            categorias_map = {}
            raw_leaders = data.get('leaders', []) or data.get('boxscore', {}).get('leaders', [])

            for item in raw_leaders:
                if 'team' in item and 'leaders' in item:
                    t_info = item.get('team', {})
                    t_abbr = str(t_info.get('abbreviation', '')).upper()
                    t_id = str(t_info.get('id', ''))
                    is_away = (t_abbr == abbrev_fora.upper() or (t_id and t_id == id_fora))

                    for cat in item.get('leaders', []):
                        cat_name = cat.get('name', '').lower()
                        cat_label = trans_cat.get(cat_name) or cat.get('displayName', '')
                        cat_key = cat_name or cat_label
                        if cat_key not in categorias_map: categorias_map[cat_key] = {"categoria": cat_label, "away": None, "home": None}
                        top_entry = (cat.get('leaders') or [{}])[0]
                        atleta = extrair_atleta(top_entry, cat_name)
                        if is_away: categorias_map[cat_key]["away"] = atleta
                        else: categorias_map[cat_key]["home"] = atleta

                elif 'name' in item and 'leaders' in item:
                    cat_name = item.get('name', '').lower()
                    cat_label = trans_cat.get(cat_name) or item.get('displayName', '')
                    cat_key = cat_name or cat_label
                    if cat_key not in categorias_map: categorias_map[cat_key] = {"categoria": cat_label, "away": None, "home": None}

                    for ldr_entry in item.get('leaders', []):
                        t_info = ldr_entry.get('team', {}) or ldr_entry.get('athlete', {}).get('team', {})
                        t_abbr = str(t_info.get('abbreviation', '')).upper()
                        t_id = str(t_info.get('id', ''))
                        is_away = (t_abbr == abbrev_fora.upper() or (t_id and t_id == id_fora))
                        atleta = extrair_atleta(ldr_entry, cat_name)
                        if is_away: categorias_map[cat_key]["away"] = atleta
                        else: categorias_map[cat_key]["home"] = atleta

            lideres_formatados = list(categorias_map.values())

        return {
            "esporte": "nfl", "timeCasa": time_casa, "logoCasa": logo_casa, "abbrevCasa": abbrev_casa,
            "placarCasa": placar_casa, "timeFora": time_fora, "logoFora": logo_fora, "abbrevFora": abbrev_fora,
            "placarFora": placar_fora, "tempo": tempo, "torneio": "NFL", "titulo_destaques": titulo_dest,
            "lideres_nfl": lideres_formatados
        }
    except Exception as e:
        print(f"Erro na extração da API da ESPN: {e}")
        return None

# ==============================================================================
# 4. EXTRAÇÃO DE DADOS DO SOFASCORE E FÓRMULA 1
# ==============================================================================
def extrair_outros_jogos_sofascore(esporte, match_id_tela, target_unique_id):
    sport_param = "basketball" if esporte == "basquete" else "football"
    script_api = f"""
    const done = arguments[arguments.length - 1];
    fetch('https://www.sofascore.com/api/v1/sport/{sport_param}/events/live')
        .then(res => res.json())
        .then(data => done((data && data.events) ? data.events : []))
        .catch(() => done([]));
    """
    try:
        raw_events = driver.execute_async_script(script_api)
        if not raw_events or not isinstance(raw_events, list): return []
    except Exception: return []

    jogos_filtrados = []
    agora_sec = int(time.time())

    for ev in raw_events:
        if match_id_tela and str(ev.get("id")) == str(match_id_tela): 
            continue
        ev_uniq_id = ev.get("tournament", {}).get("uniqueTournament", {}).get("id")
        if target_unique_id and ev_uniq_id != target_unique_id:
            continue
        id1 = ev.get("homeTeam", {}).get("id", "")
        id2 = ev.get("awayTeam", {}).get("id", "")
        p1 = ev.get("homeScore", {}).get("display", ev.get("homeScore", {}).get("current", 0))
        p2 = ev.get("awayScore", {}).get("display", ev.get("awayScore", {}).get("current", 0))

        tempo_str = "INT" if ev.get("status", {}).get("code") == 31 else ev.get("status", {}).get("description", "AO VIVO")
        
        if ev.get("status", {}).get("code") != 31 and ev.get("time", {}).get("currentPeriodStartTimestamp"):
            minuto = (ev.get("time", {}).get("initial", 0) // 60) + ((agora_sec - ev["time"]["currentPeriodStartTimestamp"]) // 60)
            if 0 <= minuto <= 130: tempo_str = f"{minuto}'"

        jogos_filtrados.append({
            "id": str(ev.get("id")), "slug": ev.get("slug", ""),
            "time1": ev.get("homeTeam", {}).get("shortName") or ev.get("homeTeam", {}).get("name", ""),
            "logo1": f"https://api.sofascore.app/api/v1/team/{id1}/image" if id1 else "", "placar1": p1,
            "time2": ev.get("awayTeam", {}).get("shortName") or ev.get("awayTeam", {}).get("name", ""),
            "logo2": f"https://api.sofascore.app/api/v1/team/{id2}/image" if id2 else "", "placar2": p2,
            "status": tempo_str, "torneio": ev.get("tournament", {}).get("name", "")
        })

    return jogos_filtrados

def atualizar_placar():
    global ultimo_tempo_valido, f1_cache_dados, f1_ultima_busca, f1_url_cache
    
    try:
        url_bruta = driver.current_url
        if not url_bruta: return "futebol"
        url_atual = url_bruta.lower()
    except Exception:
        return "futebol"
    
    # 1. ROTA DA NFL (ESPN)
    if "espn" in url_atual:
        dados_nfl = extrair_dados_espn_nfl()
        if dados_nfl:
            dados_final = cachear_todas_imagens(driver, [dados_nfl])
            with open('dados.json', 'w', encoding='utf-8') as f: 
                json.dump(dados_final, f, ensure_ascii=False, indent=4)
            return "nfl"
        return "futebol"
    
    # 2. ROTA DA FÓRMULA 1 (SESSÕES DO GP + CAMPEONATOS MUNDIAIS)
    if "formula1.com" in url_atual:
        global comando_f1_pendente, f1_url_cache
        if comando_f1_pendente:
            alvo = comando_f1_pendente
            comando_f1_pendente = None
            
            # Detecta o ano da temporada (ex: 2026) e o URL base do fim de semana
            m_ano = re.search(r'/results/(\d{4})', url_bruta)
            ano_temporada = m_ano.group(1) if m_ano else "2026"

            m_base = re.search(r'(https://www\.formula1\.com/en/results/\d+/races/\d+/[^/]+)', url_bruta)
            if m_base:
                f1_url_cache = m_base.group(1)

            base = f1_url_cache
            mapa_urls = {
                "Treino": f"{base}/practice/1" if base else "",
                "Treino 1": f"{base}/practice/1" if base else "",
                "Treino 2": f"{base}/practice/2" if base else "",
                "Treino 3": f"{base}/practice/3" if base else "",
                "Sprint": f"{base}/sprint-results" if base else "",
                "Quali": f"{base}/qualifying" if base else "",
                "Corrida": f"{base}/race-result" if base else "",
                "Pilotos": f"https://www.formula1.com/en/results/{ano_temporada}/drivers",
                "Equipes": f"https://www.formula1.com/en/results/{ano_temporada}/team"
            }
            if alvo in mapa_urls and mapa_urls[alvo]:
                driver.get(mapa_urls[alvo])
                for _ in range(25):
                    try:
                        if driver.execute_script("return document.querySelectorAll('table tbody tr').length > 0;"):
                            break
                    except Exception:
                        pass
                    time.sleep(0.08)
                url_bruta = driver.current_url
                url_atual = url_bruta.lower()

        script_f1 = """
        let table = document.querySelector('#results-table table, table[class*="table"]');
        if (!table) table = document.querySelector('table');
        if (!table) return [];

        let url = window.location.href.toLowerCase();
        let isDrivers = url.includes("/drivers");
        let isTeams = url.includes("/team");

        let headers = Array.from(table.querySelectorAll('thead th')).map(th => th.innerText.trim().toLowerCase());
        let posIdx = headers.findIndex(h => h.includes("pos"));
        let numIdx = headers.findIndex(h => h === "no." || h === "no");
        let driverIdx = headers.findIndex(h => h.includes("driver"));
        let teamIdx = headers.findIndex(h => h.includes("team"));
        let nationalityIdx = headers.findIndex(h => h.includes("nationality"));

        let q1Idx = headers.findIndex(h => h === "q1");
        let q2Idx = headers.findIndex(h => h === "q2");
        let q3Idx = headers.findIndex(h => h === "q3");
        let timeGapIdx = headers.findIndex(h => h.includes("time") || h.includes("gap") || h.includes("retired"));
        let lapsIdx = headers.findIndex(h => h.includes("laps"));
        let ptsIdx = headers.findIndex(h => h.includes("pts"));

        if (posIdx === -1) posIdx = 0;
        if (numIdx === -1 && !isTeams) numIdx = 1;

        let erroResultados = document.querySelector('.Table-module_no-result-content__WsW3A');
        if (erroResultados) return [{ pos: "", piloto: "Sem resultados", equipe: "", q1: "", q2: "", q3: "", timeGap: "", laps: "", pts: "", foto: "", logoEquipe: "", nacionalidade: "" }];

        let classificacao = [];
        let linhas = table.querySelectorAll('tbody tr');

        // MAPA OFICIAL DE NACIONALIDADES POR CÓDIGO DA F1 (GBR -> gb)
        const mapaCodigosNac = {
            "gbr": "gb", "ita": "it", "mon": "mc", "ned": "nl", "fra": "fr", "aus": "au",
            "esp": "es", "tha": "th", "jpn": "jp", "ger": "de", "bra": "br", "arg": "ar",
            "fin": "fi", "can": "ca", "mex": "mx", "nzl": "nz", "chn": "cn", "den": "dk"
        };

        linhas.forEach(linha => {
            let colunas = linha.querySelectorAll('td');
            if (colunas.length >= 2) {
                let pos = colunas[posIdx] ? colunas[posIdx].innerText.trim() : "";

                // CASO 1: CAMPEONATO DE CONSTRUTORES (EQUIPES)
                if (isTeams) {
                    let cellTeam = colunas[1];
                    let nomeEquipe = cellTeam ? cellTeam.innerText.trim() : "";
                    let imgLogo = cellTeam ? cellTeam.querySelector('img') : null;
                    let logoUrl = imgLogo ? (imgLogo.src || imgLogo.dataset?.src || '') : '';
                    let spanLogo = cellTeam ? cellTeam.querySelector('[style*="background-color"]') : null;
                    let corEquipe = spanLogo ? spanLogo.style.backgroundColor : "rgba(255,255,255,0.1)";
                    let pontos = (colunas.length > 2 && colunas[2]) ? colunas[2].innerText.trim() : "0";

                    if (pos !== "") {
                        classificacao.push({
                            pos, equipe: nomeEquipe, pts: pontos,
                            logoEquipe: logoUrl, corEquipe: corEquipe,
                            isEquipes: true
                        });
                    }
                    return;
                }

                // CASO 2: PILOTOS OU SESSÕES DO GP
                let celulaPiloto = (driverIdx !== -1 && colunas[driverIdx]) ? colunas[driverIdx] : colunas[1];
                let nomePiloto = "";
                if (celulaPiloto) {
                    let fnEl = celulaPiloto.querySelector('.max-lg\\\\:hidden, span[class*="max-lg"]');
                    let lnEl = celulaPiloto.querySelector('.max-md\\\\:hidden, span[class*="max-md"]');
                    if (fnEl && lnEl) {
                        nomePiloto = `${fnEl.innerText.trim()} ${lnEl.innerText.trim()}`;
                    } else {
                        let clone = celulaPiloto.cloneNode(true);
                        clone.querySelectorAll('img, picture, [class*="Avatar"]').forEach(e => e.remove());
                        clone.querySelectorAll('.md\\\\:hidden, [class*="md:hidden"]').forEach(e => e.remove());
                        nomePiloto = clone.innerText.trim().replace(/\\s+/g, ' ').replace(/\\b[A-Z]{3}\\b/g, '').trim();
                    }
                }

                let tagImg = celulaPiloto ? celulaPiloto.querySelector('img') : null;
                let fotoPiloto = tagImg ? (tagImg.src || tagImg.dataset?.src || '') : '';

                // Equipe, Logo e Cor da Escuderia
                let celulaEquipe = (teamIdx !== -1 && colunas[teamIdx]) ? colunas[teamIdx] : null;
                let equipe = celulaEquipe ? celulaEquipe.innerText.trim() : '';
                let imgLogo = celulaEquipe ? celulaEquipe.querySelector('img') : null;
                let logoUrl = imgLogo ? (imgLogo.src || imgLogo.dataset?.src || '') : '';
                let spanLogo = celulaEquipe ? celulaEquipe.querySelector('[style*="background-color"]') : null;
                let corEquipe = spanLogo ? spanLogo.style.backgroundColor : "transparent";

                // Nacionalidade
                let nac = "";
                if (nationalityIdx !== -1 && colunas[nationalityIdx]) {
                    let codNac = colunas[nationalityIdx].innerText.trim().toLowerCase();
                    nac = mapaCodigosNac[codNac] || codNac;
                } else {
                    let n = nomePiloto.toLowerCase();
                    if(n.includes("verstappen")) nac = "nl";
                    else if(n.includes("norris") || n.includes("hamilton") || n.includes("russell") || n.includes("bearman") || n.includes("lindblad") || n.includes("vesti")) nac = "gb";
                    else if(n.includes("leclerc")) nac = "mc";
                    else if(n.includes("sainz") || n.includes("alonso")) nac = "es";
                    else if(n.includes("piastri") || n.includes("doohan")) nac = "au";
                    else if(n.includes("perez")) nac = "mx";
                    else if(n.includes("gasly") || n.includes("ocon") || n.includes("hadjar")) nac = "fr";
                    else if(n.includes("albon")) nac = "th";
                    else if(n.includes("tsunoda") || n.includes("hirakawa") || n.includes("iwasa")) nac = "jp";
                    else if(n.includes("stroll")) nac = "ca";
                    else if(n.includes("hulkenberg")) nac = "de";
                    else if(n.includes("bottas")) nac = "fi";
                    else if(n.includes("zhou")) nac = "cn";
                    else if(n.includes("colapinto")) nac = "ar";
                    else if(n.includes("antonelli")) nac = "it";
                    else if(n.includes("lawson")) nac = "nz";
                    else if(n.includes("bortoleto")) nac = "br";
                }

                let q1 = (q1Idx !== -1 && colunas[q1Idx]) ? colunas[q1Idx].innerText.trim() : "-";
                let q2 = (q2Idx !== -1 && colunas[q2Idx]) ? colunas[q2Idx].innerText.trim() : "-";
                let q3 = (q3Idx !== -1 && colunas[q3Idx]) ? colunas[q3Idx].innerText.trim() : "-";
                let timeGap = (timeGapIdx !== -1 && colunas[timeGapIdx]) ? colunas[timeGapIdx].innerText.trim() : "-";
                let laps = (lapsIdx !== -1 && colunas[lapsIdx]) ? colunas[lapsIdx].innerText.trim() : "-";
                let pts = (ptsIdx !== -1 && colunas[ptsIdx]) ? colunas[ptsIdx].innerText.trim() : "-";

                // Flag de abandono / Desclassificação
                let timeLower = timeGap.toLowerCase();
                let isOut = (pos === "NC" || pos === "DQ" || timeLower.includes("dnf") || timeLower.includes("dns") || timeLower.includes("dsq"));

                if (pos !== "") {
                    classificacao.push({
                        pos, piloto: nomePiloto, equipe,
                        logoEquipe: logoUrl, corEquipe: corEquipe,
                        q1, q2, q3, timeGap, laps, pts,
                        foto: fotoPiloto, nacionalidade: nac,
                        isOut: isOut, isPilotos: isDrivers
                    });
                }
            }
        });
        return classificacao;
        """
        try:
            dados_tabela = driver.execute_script(script_f1)
            titulo_pagina = driver.title.split('-')[0].strip()
            
            sessao_ativa = "Corrida"
            sub_treino = ""
            if "/drivers" in url_atual:
                sessao_ativa = "Pilotos"
            elif "/team" in url_atual:
                sessao_ativa = "Equipes"
            elif "qualifying" in url_atual:
                sessao_ativa = "Quali"
            elif "practice" in url_atual:
                sessao_ativa = "Treino"
                m_pr = re.search(r'practice[/ -](\d+)', url_atual)
                sub_treino = f"Treino {m_pr.group(1)}" if m_pr else "Treino 1"
            elif "sprint" in url_atual:
                sessao_ativa = "Sprint"
            
            if dados_tabela and len(dados_tabela) > 0:
                f1_obj = {
                    "esporte": "f1",
                    "torneio": titulo_pagina,
                    "tempo": (sub_treino if sessao_ativa == "Treino" else sessao_ativa).upper(),
                    "estadio": "formula1.com",
                    "abaAtiva": sessao_ativa,
                    "subTreino": sub_treino,
                    "classificacaoF1": dados_tabela
                }
                dados_com_cache = cachear_todas_imagens(driver, [f1_obj])
                with open('dados.json', 'w', encoding='utf-8') as f: 
                    json.dump(dados_com_cache, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print("Erro F1:", e)
            
        return "f1"
    
    # 3. ROTA SOFASCORE FUTEBOL / BASQUETEBOL
    m_id = re.search(r'id:(\d+)', url_atual)
    if not m_id: return "futebol"
    
    match_id = m_id.group(1)
    esporte = "basquete" if "basketball" in url_atual or "basquete" in url_atual else "futebol"

    script_api_partida = r"""
    const done = arguments[arguments.length - 1];
    const eventId = arguments[0];
    
    function extrairRelogioDOM() {
        try {
            const seletores = [
                '[data-testid="event-status"]',
                '[data-testid="match-status"]',
                '[class*="EventStatus"]',
                '[class*="eventStatus"]',
                '[class*="HeaderStatus"]',
                '[class*="headerStatus"]'
            ];
            for (let sel of seletores) {
                let el = document.querySelector(sel);
                if (el) {
                    let m = el.innerText.match(/\b([0-1]?[0-9]:[0-5][0-9])\b/);
                    if (m) return m[1];
                }
            }

            const todos = document.querySelectorAll('span, div, p');
            for (let el of todos) {
                let txt = (el.textContent || "").trim();
                let mCompleto = txt.match(/(?:Q([1-4])|OT)\s*\(([0-1]?[0-9]:[0-5][0-9])\)/i);
                if (mCompleto) {
                    let minSeg = mCompleto[2];
                    if (minSeg.length === 4) minSeg = "0" + minSeg;
                    let qTxt = mCompleto[1] ? `${mCompleto[1]}º QUARTO` : 'OVERTIME';
                    return `${minSeg} - ${qTxt}`;
                }
            }
        } catch(e) {}
        return "";
    }

    async function obterDadosCompletos() {
        let [rEvento, rLineups, rIncidents] = await Promise.all([
            fetch(`/api/v1/event/${eventId}`).then(r => r.json()).catch(() => ({})),
            fetch(`/api/v1/event/${eventId}/lineups`).then(r => r.json()).catch(() => ({})),
            fetch(`/api/v1/event/${eventId}/incidents`).then(r => r.json()).catch(() => ({}))
        ]);

        let ev = rEvento?.event || {};
        let uId = ev?.tournament?.uniqueTournament?.id;
        let tId = ev?.tournament?.id;
        let sId = ev?.season?.id;
        let rStandings = {};
        let rCuptrees = {};

        if (!sId && uId) {
            try {
                let rSeasons = await fetch(`/api/v1/unique-tournament/${uId}/seasons`).then(r => r.json()).catch(() => ({}));
                if (rSeasons?.seasons?.length > 0) sId = rSeasons.seasons[0].id;
            } catch(e) {}
        }
        if (!sId && tId) {
            try {
                let rSeasons = await fetch(`/api/v1/tournament/${tId}/seasons`).then(r => r.json()).catch(() => ({}));
                if (rSeasons?.seasons?.length > 0) sId = rSeasons.seasons[0].id;
            } catch(e) {}
        }

        // 1. Grupos / Classificação
        if (uId && sId) {
            try {
                rStandings = await fetch(`/api/v1/unique-tournament/${uId}/season/${sId}/standings/total`).then(r => r.ok ? r.json() : {}).catch(() => ({}));
            } catch(e) {}
        }

        // 2. Mata-Mata / Cuptrees (Coleta completa sem corte de 32 IDs)
        if (uId && sId) {
            try {
                let resCup = await fetch(`/api/v1/unique-tournament/${uId}/season/${sId}/cuptrees`).then(r => r.ok ? r.json() : {}).catch(() => ({}));
                let trees = resCup?.cupTrees || resCup?.cupTree || [];

                let treeAlvo = null;
                if (Array.isArray(trees) && trees.length > 0) {
                    treeAlvo = trees.find(t => {
                        let n = (t.name || "").toLowerCase();
                        let isPre = n.includes("qualif") || n.includes("prelimin") || n.includes("pré") || n.includes("pre-");
                        return !isPre && (n.includes("knockout") || n.includes("playoff") || n.includes("final") || n.includes("eliminat") || n.includes("bracket"));
                    });

                    if (!treeAlvo) {
                        treeAlvo = trees.slice().reverse().find(t => {
                            let n = (t.name || "").toLowerCase();
                            return !n.includes("qualif") && !n.includes("prelimin") && !n.includes("pré");
                        }) || trees[trees.length - 1];
                    }
                }

                let dTree = null;
                if (treeAlvo?.id) {
                    let tid = treeAlvo.id;
                    let [d1, d2] = await Promise.all([
                        fetch(`/api/v1/cup-tree/${tid}`).then(r => r.ok ? r.json() : null).catch(() => null),
                        fetch(`/api/v1/unique-tournament/${uId}/season/${sId}/cuptree/${tid}`).then(r => r.ok ? r.json() : null).catch(() => null)
                    ]);
                    dTree = d1 || d2;
                }

                let arvoreFinal = dTree || treeAlvo || resCup;

                // Coleta eventos já existentes na resposta da API
                let eventosDetalhados = {};
                function registrarEvento(ev) {
                    if (ev && ev.id && (ev.homeScore !== undefined || ev.status !== undefined)) {
                        eventosDetalhados[String(ev.id)] = ev;
                    }
                }

                if (Array.isArray(resCup?.events)) resCup.events.forEach(registrarEvento);
                if (Array.isArray(dTree?.events)) dTree.events.forEach(registrarEvento);

                // Coleta todos os IDs da árvore eliminatória
                let idsSet = new Set();
                function coletarIds(obj) {
                    if (!obj || typeof obj !== 'object') return;
                    if (Array.isArray(obj)) {
                        obj.forEach(coletarIds);
                    } else {
                        if (Array.isArray(obj.events)) {
                            obj.events.forEach(id => {
                                if (typeof id === 'number' || typeof id === 'string') idsSet.add(id);
                                else if (id && id.id) { idsSet.add(id.id); registrarEvento(id); }
                            });
                        }
                        if (Array.isArray(obj.matches)) {
                            obj.matches.forEach(id => {
                                if (typeof id === 'number' || typeof id === 'string') idsSet.add(id);
                                else if (id && id.id) { idsSet.add(id.id); registrarEvento(id); }
                            });
                        }
                        Object.values(obj).forEach(coletarIds);
                    }
                }
                coletarIds(arvoreFinal);

                // Busca apenas os IDs que ainda não vieram inclusos na resposta
                let listaIds = Array.from(idsSet).filter(id => !eventosDetalhados[String(id)]);
                if (listaIds.length > 0) {
                    let promessas = listaIds.slice(0, 64).map(id =>
                        fetch(`/api/v1/event/${id}`)
                            .then(r => r.ok ? r.json() : null)
                            .then(j => j && j.event ? j.event : null)
                            .catch(() => null)
                    );
                    let resps = await Promise.all(promessas);
                    resps.forEach(registrarEvento);
                }

                rCuptrees = {
                    tree: arvoreFinal,
                    eventsMap: eventosDetalhados
                };
            } catch(e) {}
        }

        return {
            evento: rEvento || {},
            lineups: rLineups || {},
            incidents: rIncidents || {},
            standings: rStandings || {},
            cuptrees: rCuptrees || {},
            relogioDom: extrairRelogioDOM(),
            campanhaBasquete: {}
        };
    }
    
    obterDadosCompletos().then(res => done(res)).catch(() => done(null));
    """
    
    try:
        dados = driver.execute_async_script(script_api_partida, match_id)
        if not dados: return esporte
        if isinstance(dados, dict):
            evento_data = dados.get("evento", {}).get("event", {})
            lineups_data = dados.get("lineups", {})
            standings_data = dados.get("standings", {})
            cuptrees_data = dados.get("cuptrees", {})
            incidents_data = dados.get("incidents", {}).get("incidents", [])
            relogio_dom = dados.get("relogioDom", "")
            campanha_basquete = dados.get("campanhaBasquete", {})
        elif isinstance(dados, list) and len(dados) >= 3:
            evento_data = dados[0].get("event", {}) if isinstance(dados[0], dict) else {}
            lineups_data = dados[1] if isinstance(dados[1], dict) else {}
            incidents_data = dados[2].get("incidents", []) if isinstance(dados[2], dict) else []
            relogio_dom = dados[3] if len(dados) > 3 and isinstance(dados[3], str) else ""
            standings_data = {}
            cuptrees_data = {}
            campanha_basquete = {}
        else: return esporte

        time_casa = evento_data.get("homeTeam", {}).get("shortName") or evento_data.get("homeTeam", {}).get("name", "Casa")
        id_casa = evento_data.get("homeTeam", {}).get("id", "")
        logo_casa = f"https://api.sofascore.app/api/v1/team/{id_casa}/image" if id_casa else ""
        time_fora = evento_data.get("awayTeam", {}).get("shortName") or evento_data.get("awayTeam", {}).get("name", "Fora")
        id_fora = evento_data.get("awayTeam", {}).get("id", "")
        logo_fora = f"https://api.sofascore.app/api/v1/team/{id_fora}/image" if id_fora else ""
        placar_casa = str(evento_data.get("homeScore", {}).get("display", evento_data.get("homeScore", {}).get("current", 0)))
        placar_fora = str(evento_data.get("awayScore", {}).get("display", evento_data.get("awayScore", {}).get("current", 0)))
        torneio = evento_data.get("tournament", {}).get("name", "")
        venue_info = evento_data.get("venue", {})
        estadio = venue_info.get("stadium", {}).get("name") or venue_info.get("city", {}).get("name", "")

        penaltis_seq_casa, penaltis_seq_fora = [], []
        score_pen_casa, score_pen_fora = 0, 0
        for inc in reversed(incidents_data):
            if inc.get("incidentType") == "penaltyShootout":
                is_home = inc.get("isHome")
                is_scored = (inc.get("incidentClass") == "scored")
                if is_home:
                    penaltis_seq_casa.append(is_scored)
                    if is_scored: score_pen_casa += 1
                else:
                    penaltis_seq_fora.append(is_scored)
                    if is_scored: score_pen_fora += 1
        tem_penaltis = len(penaltis_seq_casa) > 0 or len(penaltis_seq_fora) > 0

        status_code = evento_data.get("status", {}).get("code")
        status_desc = evento_data.get("status", {}).get("description", "AO VIVO")
        agora_sec = int(time.time())
        tempo_str = "AO VIVO"
        
        if status_code == 31: tempo_str = "INTERVALO"
        elif status_code in [100, 110, 120, 9]: tempo_str = "FIM"
        elif esporte == "futebol":
            if status_code in [6, 7, 33, 35] and evento_data.get("time", {}).get("currentPeriodStartTimestamp"):
                inicio = evento_data["time"]["currentPeriodStartTimestamp"]
                minuto_base = evento_data.get("time", {}).get("initial", 0) // 60
                decorrido = (agora_sec - inicio) // 60
                minuto_atual = minuto_base + decorrido
                if status_code == 6:
                    inj = evento_data.get("time", {}).get("injuryTime1", 0)
                    tempo_str = f"45' +{inj}" if (minuto_atual >= 45 and inj > 0) else f"{minuto_atual}'"
                elif status_code == 7:
                    inj = evento_data.get("time", {}).get("injuryTime2", 0)
                    tempo_str = f"90' +{inj}" if (minuto_atual >= 90 and inj > 0) else f"{minuto_atual}'"
                else: tempo_str = f"{minuto_atual}'"
            else:
                traducao_fut = { "Not started": "EM BREVE", "Postponed": "ADIADO", "Cancelled": "CANCELADO", "Delayed": "ATRASADO", "Interrupted": "INTERROMPIDO", "Suspended": "SUSPENSO", "Pause": "PAUSA", "Awaiting penalties": "AGUARD. PEN", "Awaiting extra time": "AGUARD. PRO", "Penalty shootout": "PÊNALTIS", "Extra time halftime": "INT PRO", "Extra time": "PRORROGAÇÃO" }
                tempo_str = traducao_fut.get(status_desc, status_desc).upper()
                if "ESPERANDO PÊNALTIS" in tempo_str or "AWAITING PENALTIES" in tempo_str: tempo_str = "AGUARD. PEN"
        else:
            traducao = { "1st quarter": "1º QUARTO", "2nd quarter": "2º QUARTO", "3rd quarter": "3º QUARTO", "4th quarter": "4º QUARTO", "Halftime": "INTERVALO", "Pause": "PAUSA", "Ended": "FIM", "Awaiting extra time": "AGUARD. OT", "Extra time": "OVERTIME", "Overtime": "OVERTIME" }
            quarto_txt = traducao.get(status_desc, status_desc).upper()
            if status_code == 31 or "INTERVALO" in quarto_txt or "HALFTIME" in str(status_desc).upper(): tempo_str = "INTERVALO"
            elif status_code in [100, 110, 120, 9] or "FIM" in quarto_txt or "ENDED" in str(status_desc).upper(): tempo_str = "FIM"
            elif "PAUSA" in quarto_txt: tempo_str = "PAUSA"
            else:
                if relogio_dom and "QUARTO" in relogio_dom: tempo_str = relogio_dom
                elif relogio_dom: tempo_str = f"{relogio_dom} - {quarto_txt}"
                else: tempo_str = quarto_txt
            
        ultimo_tempo_valido = tempo_str

        esc_casa, esc_fora = [], []
        if esporte == "basquete":
            campanha = campanha_basquete if isinstance(campanha_basquete, dict) else {}
            formacao_casa = campanha.get("casa") or lineups_data.get("home", {}).get("formation", "")
            formacao_fora = campanha.get("fora") or lineups_data.get("away", {}).get("formation", "")
        else:
            formacao_casa = lineups_data.get("home", {}).get("formation", "")
            formacao_fora = lineups_data.get("away", {}).get("formation", "")

        def formatar_jogadores(time_lineup, is_home):
            jogadores = []
            for p in time_lineup.get("players", []):
                player_info = p.get("player", {})
                estatisticas = p.get("statistics", {})
                p_id = player_info.get("id")
                gols_marcados = sum(1 for inc in incidents_data if inc.get("incidentType") == "goal" and inc.get("incidentClass") != "ownGoal" and inc.get("player", {}).get("id") == p_id)
                gols_contra = sum(1 for inc in incidents_data if inc.get("incidentType") == "goal" and inc.get("incidentClass") == "ownGoal" and inc.get("player", {}).get("id") == p_id)
                assistencias = sum(1 for inc in incidents_data if inc.get("incidentType") == "goal" and inc.get("assist1", {}).get("id") == p_id)
                amarelo = any(inc.get("incidentType") == "card" and inc.get("incidentClass") == "yellow" and inc.get("player", {}).get("id") == p_id for inc in incidents_data)
                vermelho = any(inc.get("incidentType") == "card" and inc.get("incidentClass") in ["red", "yellowRed"] and inc.get("player", {}).get("id") == p_id for inc in incidents_data)
                sub_out = next((inc for inc in incidents_data if inc.get("incidentType") == "substitution" and inc.get("playerOut", {}).get("id") == p_id), None)
                sub_in = next((inc for inc in incidents_data if inc.get("incidentType") == "substitution" and inc.get("playerIn", {}).get("id") == p_id), None)
                nacionalidade = player_info.get("country", {}).get("alpha2", "").lower()
                correcoes_bandeiras = {"en": "gb-eng", "sx": "gb-sct", "sc": "gb-sct", "wa": "gb-wls", "wl": "gb-wls", "ni": "gb-nir"}
                nacionalidade = correcoes_bandeiras.get(nacionalidade, nacionalidade)
                rating = estatisticas.get("rating", "-")
                try: rating = f"{float(rating):.1f}"
                except (ValueError, TypeError): pass

                jogadores.append({
                    "numero": p.get("shirtNumber", "-"), "nome": player_info.get("shortName", player_info.get("name", "")),
                    "nacionalidade": nacionalidade, "capitao": p.get("captain", False),
                    "foto": f"https://api.sofascore.app/api/v1/player/{p_id}/image" if p_id else "",
                    "rating": rating, "gol": gols_marcados > 0, "gols_count": gols_marcados,
                    "gol_contra": gols_contra > 0, "gols_contra_count": gols_contra,
                    "assist": assistencias > 0, "assists_count": assistencias,
                    "amarelo": amarelo, "vermelho": vermelho, "saiu": bool(sub_out), "entrou": bool(sub_in),
                    "lesao": bool(sub_out and sub_out.get("incidentClass") == "injury"),
                    "sub_nome": sub_out.get("playerIn", {}).get("shortName", "") if sub_out else (sub_in.get("playerOut", {}).get("shortName", "") if sub_in else ""),
                    "pts": estatisticas.get("points", "-"), "reb": estatisticas.get("rebounds", "-"),
                    "ast": estatisticas.get("assists", "-"), "reserva": p.get("substitute", False)
                })
            return jogadores

        if lineups_data.get("home"): esc_casa = formatar_jogadores(lineups_data["home"], True)
        if lineups_data.get("away"): esc_fora = formatar_jogadores(lineups_data["away"], False)

        id_do_campeonato = evento_data.get("tournament", {}).get("uniqueTournament", {}).get("id")
        outros_jogos = extrair_outros_jogos_sofascore(esporte, match_id, id_do_campeonato)
        
      # 1. PROCESSAR TODOS OS GRUPOS / CLASSIFICAÇÃO (FUTEBOL E BASQUETE)
        tabelas_grupos = []
        tabela_classificacao = []
        if (esporte in ["futebol", "basquete"]) and standings_data:
            standings_list = standings_data.get("standings", [])
            for grp in standings_list:
                if not isinstance(grp, dict): continue
                nome_grp = grp.get("name") or grp.get("groupName") or "Classificação"
                linhas_grp = []
                for r in grp.get("rows", []):
                    if not isinstance(r, dict): continue
                    tm = r.get("team") if isinstance(r.get("team"), dict) else {}
                    t_id = tm.get("id")
                    diff = r.get("scoreDiffFormatted")
                    if diff is None:
                        diff = r.get("scoresFor", 0) - r.get("scoresAgainst", 0)
                        diff = f"+{diff}" if diff > 0 else str(diff)

                    promo_obj = r.get("promotion")
                    promo_txt = promo_obj.get("text", "") if isinstance(promo_obj, dict) else str(promo_obj or "")

                    pos_atual = r.get("position")
                    
                    # Registo de variação de posições (Abordagem 1)
                    chave_time = f"{match_id}_{nome_grp}_{t_id}"
                    if chave_time not in posicoes_iniciais_times and pos_atual is not None:
                        posicoes_iniciais_times[chave_time] = pos_atual

                    pos_base = posicoes_iniciais_times.get(chave_time, pos_atual)
                    variacao = 0
                    if pos_base is not None and pos_atual is not None:
                        variacao = pos_base - pos_atual

                    # Aproveitamento / Percentagem de vitórias no basquetebol (ex: 0.650 -> .650)
                    pct_raw = r.get("percentage")
                    pct_str = ""
                    if pct_raw is not None:
                        try:
                            f_pct = float(pct_raw)
                            pct_str = f"{f_pct:.3f}".lstrip("0") if f_pct <= 1.0 else f"{f_pct:.1f}%"
                        except Exception:
                            pct_str = str(pct_raw)

                    linhas_grp.append({
                        "pos": pos_atual,
                        "variacao": variacao,
                        "id": t_id,
                        "nome": tm.get("shortName") or tm.get("name", ""),
                        "promocao": promo_txt,
                        "logo": f"https://api.sofascore.app/api/v1/team/{t_id}/image" if t_id else "",
                        "jogos": r.get("matches", 0),
                        "v": r.get("wins", 0),
                        "e": r.get("draws", 0),
                        "d": r.get("losses", 0),
                        "sg": str(diff),
                        "pts": r.get("points", 0),
                        "pct": pct_str,
                        "isCasa": str(t_id) == str(id_casa),
                        "isFora": str(t_id) == str(id_fora)
                    })
                
                tem_time_jogo = any(t["isCasa"] or t["isFora"] for t in linhas_grp)
                tabelas_grupos.append({
                    "grupo": nome_grp,
                    "ativoPadrao": tem_time_jogo,
                    "times": linhas_grp
                })

            grupo_principal = next((g for g in tabelas_grupos if g["ativoPadrao"]), None)
            if not grupo_principal and tabelas_grupos:
                grupo_principal = tabelas_grupos[0]
            if grupo_principal:
                tabela_classificacao = grupo_principal["times"]

      # 2. PROCESSAR O MATA-MATA (FUTEBOL E BASQUETE)
        matamata_fases = []
        if (esporte in ["futebol", "basquete"]) and cuptrees_data:
            rounds_encontrados = []

            def buscar_rounds_recursivo(obj):
                if not obj: return
                if isinstance(obj, dict):
                    if "rounds" in obj and isinstance(obj["rounds"], list) and len(obj["rounds"]) > 0:
                        rounds_encontrados.extend(obj["rounds"])
                        return
                    for k, v in obj.items():
                        if k in ["tree", "selectedTree", "views", "cupTree", "cupTrees"]:
                            if isinstance(v, (dict, list)):
                                buscar_rounds_recursivo(v)
                        elif k != "eventsMap":
                            if isinstance(v, (dict, list)):
                                buscar_rounds_recursivo(v)
                elif isinstance(obj, list):
                    for item in obj:
                        buscar_rounds_recursivo(item)

            buscar_rounds_recursivo(cuptrees_data)

            mapa_eventos = cuptrees_data.get("eventsMap", {}) if isinstance(cuptrees_data, dict) else {}

            def extrair_num(val):
                if val is None or val == "": return None
                if isinstance(val, dict):
                    v = val.get("display", val.get("current", val.get("score")))
                    if v is not None:
                        try: return int(v)
                        except Exception: pass
                    return None
                try: return int(val)
                except Exception: return None

            def obter_time_info(tm_obj):
                if not tm_obj: return "", "A definir"
                if isinstance(tm_obj, dict):
                    t_id = str(tm_obj.get("id", ""))
                    t_nome = tm_obj.get("shortName") or tm_obj.get("name") or tm_obj.get("slug") or "A definir"
                    return t_id, t_nome
                return str(tm_obj), str(tm_obj)

            def obter_status_texto(obj):
                if not isinstance(obj, dict): return str(obj or "")
                st = obj.get("status")
                if isinstance(st, dict): return str(st.get("description") or st.get("type") or "")
                return str(st or "")

            def extrair_penaltis_evento(ev):
                if not isinstance(ev, dict) or esporte == "basquete": return None, None
                hs = ev.get("homeScore") if isinstance(ev.get("homeScore"), dict) else {}
                aws = ev.get("awayScore") if isinstance(ev.get("awayScore"), dict) else {}
                
                p_h = None
                p_a = None
                for k in ["penalties", "shootout", "penalty", "penaltyScore", "p"]:
                    if p_h is None and hs.get(k) is not None: p_h = hs.get(k)
                    if p_a is None and aws.get(k) is not None: p_a = aws.get(k)
                
                if p_h is None and ev.get("homePenaltyScore") is not None:
                    p_h = ev.get("homePenaltyScore")
                if p_a is None and ev.get("awayPenaltyScore") is not None:
                    p_a = ev.get("awayPenaltyScore")

                return extrair_num(p_h), extrair_num(p_a)

            for rnd in rounds_encontrados:
                if not isinstance(rnd, dict): continue

                nome_fase = rnd.get("description") or rnd.get("name") or rnd.get("slug") or "Eliminatória"
                nome_low = nome_fase.lower()

                if any(p in nome_low for p in ["qualif", "prelimin", "pré", "pre-", "fase prévia"]):
                    continue

                confrontos = []
                blocos = rnd.get("blocks") or rnd.get("events") or rnd.get("matches") or []

                for blk in blocos:
                    if not isinstance(blk, dict): continue

                    raw_events = blk.get("events") or blk.get("matches") or []
                    eventos_internos = []
                    if isinstance(raw_events, list):
                        for item in raw_events:
                            if isinstance(item, dict):
                                eventos_internos.append(item)
                            elif isinstance(item, (int, str)):
                                ev_key = str(item)
                                if ev_key in mapa_eventos:
                                    eventos_internos.append(mapa_eventos[ev_key])

                    eventos_internos.sort(key=lambda x: x.get("startTimestamp", 0) if isinstance(x, dict) else 0)

                    h_tm = None
                    a_tm = None
                    scores_parts_0 = None
                    scores_parts_1 = None
                    pen_part_0 = None
                    pen_part_1 = None

                    parts = blk.get("participants") or blk.get("competitors") or blk.get("teams") or []
                    if isinstance(parts, list) and len(parts) >= 2:
                        p0, p1 = parts[0], parts[1]
                        h_tm = p0.get("team") if (isinstance(p0, dict) and "team" in p0) else p0
                        a_tm = p1.get("team") if (isinstance(p1, dict) and "team" in p1) else p1
                        
                        if isinstance(p0, dict):
                            if isinstance(p0.get("scores"), list): scores_parts_0 = [extrair_num(x) for x in p0["scores"]]
                            for pk in ["penalties", "shootout", "penaltyScore", "penalty"]:
                                if p0.get(pk) is not None: pen_part_0 = extrair_num(p0.get(pk)); break
                        if isinstance(p1, dict):
                            if isinstance(p1.get("scores"), list): scores_parts_1 = [extrair_num(x) for x in p1["scores"]]
                            for pk in ["penalties", "shootout", "penaltyScore", "penalty"]:
                                if p1.get(pk) is not None: pen_part_1 = extrair_num(p1.get(pk)); break

                    if not h_tm:
                        h_tm = blk.get("homeTeam") or blk.get("team1")
                        a_tm = blk.get("awayTeam") or blk.get("team2")

                    if not h_tm and eventos_internos:
                        ev0 = eventos_internos[0]
                        if isinstance(ev0, dict):
                            h_tm = ev0.get("homeTeam") or ev0.get("team1")
                            a_tm = ev0.get("awayTeam") or ev0.get("team2")

                    h_id, nome1 = obter_time_info(h_tm)
                    a_id, nome2 = obter_time_info(a_tm)

                    is_jogo_atual = False
                    if id_casa and id_fora:
                        cond_id = (str(h_id) == str(id_casa) and str(a_id) == str(id_fora)) or (str(h_id) == str(id_fora) and str(a_id) == str(id_casa))
                        n1_low, n2_low = nome1.lower(), nome2.lower()
                        tc_low, tf_low = str(time_casa).lower(), str(time_fora).lower()
                        cond_nome = (tc_low in n1_low or n1_low in tc_low) and (tf_low in n2_low or n2_low in tf_low)
                        cond_nome_inv = (tf_low in n1_low or n1_low in tf_low) and (tc_low in n2_low or n2_low in tc_low)
                        if cond_id or cond_nome or cond_nome_inv:
                            is_jogo_atual = True

                    pernas_textos = []
                    total_t1 = 0
                    total_t2 = 0
                    teve_jogo_resolvido = False
                    p1_pen = pen_part_0
                    p2_pen = pen_part_1

                    # BASQUETE: Pontuação é série (ex: 4 a 2 vitórias) ou jogo único
                    if esporte == "basquete":
                        sc1_b = None
                        sc2_b = None
                        if parts and len(parts) >= 2:
                            sc1_b = extrair_num(parts[0].get("score") if isinstance(parts[0], dict) else None)
                            sc2_b = extrair_num(parts[1].get("score") if isinstance(parts[1], dict) else None)
                        
                        if sc1_b is not None and sc2_b is not None:
                            total_t1, total_t2 = sc1_b, sc2_b
                            teve_jogo_resolvido = True
                            if len(eventos_internos) > 0:
                                pernas_textos.append(f"Série ({sc1_b}-{sc2_b})")

                    # FUTEBOL: Ida e Volta com array de scores em participants
                    elif scores_parts_0 and scores_parts_1 and len(scores_parts_0) >= 2 and len(scores_parts_1) >= 2:
                        s0_ida, s0_volta = scores_parts_0[0], scores_parts_0[1]
                        s1_ida, s1_volta = scores_parts_1[0], scores_parts_1[1]

                        if s0_ida is not None and s1_ida is not None:
                            pernas_textos.append(f"Ida: {s0_ida}-{s1_ida}")
                            total_t1 += s0_ida
                            total_t2 += s1_ida
                            teve_jogo_resolvido = True

                        if s0_volta is not None and s1_volta is not None:
                            pernas_textos.append(f"Volta: {s0_volta}-{s1_volta}")
                            total_t1 += s0_volta
                            total_t2 += s1_volta
                            teve_jogo_resolvido = True

                    # FUTEBOL: Ida e Volta com eventos associados
                    elif esporte == "futebol" and len(eventos_internos) >= 2:
                        for idx, ev in enumerate(eventos_internos[:2]):
                            rotulo = "Ida" if idx == 0 else "Volta"
                            ev_hid = str(ev.get("homeTeam", {}).get("id", ""))

                            sc_h = extrair_num(ev.get("homeScore"))
                            sc_a = extrair_num(ev.get("awayScore"))

                            pen_h, pen_a = extrair_penaltis_evento(ev)
                            if pen_h is not None and pen_a is not None:
                                p1_pen = pen_h if ev_hid == h_id else pen_a
                                p2_pen = pen_a if ev_hid == h_id else pen_h

                            if sc_h is not None and sc_a is not None:
                                g_t1 = sc_h if ev_hid == str(h_id) else sc_a
                                g_t2 = sc_a if ev_hid == str(h_id) else sc_h
                                total_t1 += g_t1
                                total_t2 += g_t2
                                pernas_textos.append(f"{rotulo}: {g_t1}-{g_t2}")
                                teve_jogo_resolvido = True
                            else:
                                st_desc = obter_status_texto(ev)
                                if st_desc and st_desc.lower() not in ["not started", "em breve"]:
                                    pernas_textos.append(f"{rotulo}: {st_desc}")

                    # Fallback amplo em participantes / bloco
                    if not teve_jogo_resolvido:
                        raw_h = None
                        raw_a = None

                        if parts and len(parts) >= 2:
                            p0, p1 = parts[0], parts[1]
                            if isinstance(p0, dict) and isinstance(p1, dict):
                                for k in ["score", "aggregatedScore", "aggregateScore", "goals", "points", "value"]:
                                    if raw_h is None and p0.get(k) is not None: raw_h = p0.get(k)
                                    if raw_a is None and p1.get(k) is not None: raw_a = p1.get(k)

                        if raw_h is None or raw_a is None:
                            for kh, ka in [("aggregatedHomeScore", "aggregatedAwayScore"),
                                          ("aggregateHomeScore", "aggregateAwayScore"),
                                          ("homeTeamScore", "awayTeamScore"),
                                          ("homeScore", "awayScore"),
                                          ("score1", "score2")]:
                                if raw_h is None and blk.get(kh) is not None: raw_h = blk.get(kh)
                                if raw_a is None and blk.get(ka) is not None: raw_a = blk.get(ka)

                        h_num = extrair_num(raw_h)
                        a_num = extrair_num(raw_a)

                        if h_num is not None and a_num is not None:
                            placar1_final = str(h_num)
                            placar2_final = str(a_num)
                            teve_jogo_resolvido = True
                        else:
                            placar1_final = "-"
                            placar2_final = "-"
                    else:
                        placar1_final = str(total_t1)
                        placar2_final = str(total_t2)

                    penaltis_str = f" (Pên: {p1_pen}-{p2_pen})" if (p1_pen is not None and p2_pen is not None) else ""
                    
                    if len(pernas_textos) > 0:
                        status_final = " • ".join(pernas_textos) + penaltis_str
                    else:
                        base_st = obter_status_texto(blk)
                        if not base_st:
                            base_st = "FIM" if (teve_jogo_resolvido and placar1_final != "-") else "EM BREVE"
                        status_final = (base_st + penaltis_str).strip()

                    confrontos.append({
                        "time1": nome1,
                        "logo1": f"https://api.sofascore.app/api/v1/team/{h_id}/image" if h_id else "",
                        "placar1": placar1_final,
                        "pen1": str(p1_pen) if p1_pen is not None else None,
                        "time2": nome2,
                        "logo2": f"https://api.sofascore.app/api/v1/team/{a_id}/image" if a_id else "",
                        "placar2": placar2_final,
                        "pen2": str(p2_pen) if p2_pen is not None else None,
                        "status": status_final,
                        "isJogoAtual": is_jogo_atual
                    })

                if confrontos:
                    matamata_fases.append({
                        "fase": nome_fase,
                        "jogos": confrontos
                    })
                    
            
                
        jogo = [{
            "esporte": esporte, "timeCasa": time_casa, "logoCasa": logo_casa, "formacaoCasa": formacao_casa,
            "escalacaoCasa": esc_casa, "placarCasa": placar_casa, "timeFora": time_fora, "logoFora": logo_fora,
            "formacaoFora": formacao_fora, "escalacaoFora": esc_fora, "placarFora": placar_fora,
            "temPenaltis": tem_penaltis, "scorePenCasa": score_pen_casa, "scorePenFora": score_pen_fora,
            "seqPenCasa": penaltis_seq_casa, "seqPenFora": penaltis_seq_fora,
            "tempo": ultimo_tempo_valido, "estadio": estadio, "torneio": torneio,
            "outros_jogos": outros_jogos,
            "tabela": tabela_classificacao,
            "grupos": tabelas_grupos,
            "matamata": matamata_fases
        }]
            
        jogo_final = cachear_todas_imagens(driver, jogo)
        with open('dados.json', 'w', encoding='utf-8') as f: 
            json.dump(jogo_final, f, ensure_ascii=False, indent=4)

    except Exception as e:
        print(f"Erro na extração da API Sofascore: {e}")
        
    return esporte


# LOOP PRINCIPAL
contador_ciclos = 0
try:
    while True:
        esp = atualizar_placar()
        contador_ciclos += 1
        
        if contador_ciclos % 10 == 0:
            gc.collect()

        # Espera até 1.5s, mas acorda imediatamente se você clicar em qualquer botão
        for _ in range(15):
            if comando_f1_pendente:
                break
            time.sleep(0.1)
            
except KeyboardInterrupt:
    print("\nEncerrando leitura do placar...")