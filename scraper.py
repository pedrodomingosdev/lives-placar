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
        let sId = ev?.season?.id;
        let rStandings = {};
        let rCuptrees = {};

        if (uId && !sId) {
            try {
                let rSeasons = await fetch(`/api/v1/unique-tournament/${uId}/seasons`).then(r => r.json());
                if (rSeasons?.seasons?.length > 0) sId = rSeasons.seasons[0].id;
            } catch(e) {}
        }

        if (uId && sId) {
            try {
                let [resSt, resCup] = await Promise.all([
                    fetch(`/api/v1/unique-tournament/${uId}/season/${sId}/standings/total`).then(r => r.ok ? r.json() : {}).catch(() => ({})),
                    fetch(`/api/v1/unique-tournament/${uId}/season/${sId}/cuptrees`).then(r => r.ok ? r.json() : {}).catch(() => ({}))
                ]);
                rStandings = resSt || {};
                rCuptrees = resCup || {};
                if (!rCuptrees || Object.keys(rCuptrees).length === 0) {
                    try {
                        let r2 = await fetch(`/api/v1/unique-tournament/${uId}/season/${sId}/cuptree`).then(r => r.ok ? r.json() : {}).catch(() => ({}));
                        if (r2 && Object.keys(r2).length > 0) rCuptrees = r2;
                    } catch(e) {}
                }
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
        
        # 1. PROCESSAR TODOS OS GRUPOS / CLASSIFICAÇÃO
        tabelas_grupos = []
        tabela_classificacao = []
        if esporte == "futebol" and standings_data:
            standings_list = standings_data.get("standings", [])
            for grp in standings_list:
                nome_grp = grp.get("name") or grp.get("groupName") or "Classificação"
                linhas_grp = []
                for r in grp.get("rows", []):
                    tm = r.get("team", {})
                    t_id = tm.get("id")
                    diff = r.get("scoreDiffFormatted")
                    if diff is None:
                        diff = r.get("scoresFor", 0) - r.get("scoresAgainst", 0)
                        diff = f"+{diff}" if diff > 0 else str(diff)

                    linhas_grp.append({
                        "pos": r.get("position"),
                        "id": t_id,
                        "nome": tm.get("shortName") or tm.get("name", ""),
                        "promocao": r.get("promotion", {}).get("text", ""),
                        "logo": f"https://api.sofascore.app/api/v1/team/{t_id}/image" if t_id else "",
                        "jogos": r.get("matches", 0),
                        "v": r.get("wins", 0),
                        "e": r.get("draws", 0),
                        "d": r.get("losses", 0),
                        "sg": str(diff),
                        "pts": r.get("points", 0),
                        "isCasa": str(t_id) == str(id_casa),
                        "isFora": str(t_id) == str(id_fora)
                    })
                
                tem_time_jogo = any(t["isCasa"] or t["isFora"] for t in linhas_grp)
                tabelas_grupos.append({
                    "grupo": nome_grp,
                    "ativoPadrao": tem_time_jogo,
                    "times": linhas_grp
                })

            # Tabela simples de fallback (grupo do jogo atual)
            grupo_principal = next((g for g in tabelas_grupos if g["ativoPadrao"]), None)
            if not grupo_principal and tabelas_grupos:
                grupo_principal = tabelas_grupos[0]
            if grupo_principal:
                tabela_classificacao = grupo_principal["times"]

        # 2. PROCESSAR O MATA-MATA (CHAVEAMENTO RESILIENTE)
        matamata_fases = []
        if esporte == "futebol" and cuptrees_data:
            arvores = []
            if isinstance(cuptrees_data, dict):
                arvores = cuptrees_data.get("cupTrees") or cuptrees_data.get("cupTree") or cuptrees_data.get("rounds") or []
            elif isinstance(cuptrees_data, list):
                arvores = cuptrees_data

            if isinstance(arvores, dict):
                arvores = [arvores]

            rounds = []
            if arvores and isinstance(arvores, list):
                for arv in arvores:
                    if isinstance(arv, dict) and "rounds" in arv:
                        rounds.extend(arv.get("rounds", []))
                    elif isinstance(arv, dict):
                        rounds.append(arv)

            for rnd in rounds:
                if not isinstance(rnd, dict): continue
                nome_fase = rnd.get("description") or rnd.get("name") or "Eliminatória"
                confrontos = []
                blocos = rnd.get("blocks") or rnd.get("events") or rnd.get("matches") or []

                for blk in blocos:
                    if not isinstance(blk, dict): continue
                    eventos = blk.get("events") or blk.get("matches") or []
                    if not eventos and blk.get("event"): eventos = [blk.get("event")]
                    if not eventos and blk.get("match"): eventos = [blk.get("match")]
                    if not eventos and (blk.get("homeTeam") or blk.get("team1")):
                        eventos = [blk]

                    for ev in eventos:
                        if not isinstance(ev, dict): continue
                        h_tm = ev.get("homeTeam") or ev.get("team1") or {}
                        a_tm = ev.get("awayTeam") or ev.get("team2") or {}
                        h_id = h_tm.get("id")
                        a_id = a_tm.get("id")
                        h_sc = ev.get("homeScore", {}).get("display", ev.get("homeScore", {}).get("current", "-"))
                        a_sc = ev.get("awayScore", {}).get("display", ev.get("awayScore", {}).get("current", "-"))
                        status_ev = ev.get("status", {}).get("description", "")

                        confrontos.append({
                            "time1": h_tm.get("shortName") or h_tm.get("name", "A definir"),
                            "logo1": f"https://api.sofascore.app/api/v1/team/{h_id}/image" if h_id else "",
                            "placar1": str(h_sc) if h_sc is not None else "-",
                            "time2": a_tm.get("shortName") or a_tm.get("name", "A definir"),
                            "logo2": f"https://api.sofascore.app/api/v1/team/{a_id}/image" if a_id else "",
                            "placar2": str(a_sc) if a_sc is not None else "-",
                            "status": status_ev,
                            "isJogoAtual": (str(h_id) in [str(id_casa), str(id_fora)]) or (str(a_id) in [str(id_casa), str(id_fora)])
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