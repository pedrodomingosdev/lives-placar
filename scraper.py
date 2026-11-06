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
        
        cbs = item.get("cbs_nfl", {})
        if isinstance(cbs, dict):
            for side in ["away_stats", "home_stats"]:
                st_side = cbs.get(side, {})
                # Ataque
                for cat in ["passing", "rushing", "receiving"]:
                    for p in st_side.get("offense", {}).get(cat, []):
                        if p.get("foto"): urls_para_descarregar.add(p["foto"])
                # Defesa
                for p in st_side.get("defense", []):
                    if p.get("foto"): urls_para_descarregar.add(p["foto"])
                # Times especiais
                for cat in ["kicking", "punting", "kickReturns", "puntReturns"]:
                    for p in st_side.get("specialTeams", {}).get(cat, []):
                        if p.get("foto"): urls_para_descarregar.add(p["foto"])

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

        cbs = item.get("cbs_nfl", {})
        if isinstance(cbs, dict):
            for side in ["away_stats", "home_stats"]:
                st_side = cbs.get(side, {})
                # Ataque
                for cat in ["passing", "rushing", "receiving"]:
                    for p in st_side.get("offense", {}).get(cat, []):
                        if p.get("foto") in mapa_cache:
                            p["foto"] = mapa_cache[p["foto"]]
                # Defesa
                for p in st_side.get("defense", []):
                    if p.get("foto") in mapa_cache:
                        p["foto"] = mapa_cache[p["foto"]]
                # Times especiais
                for cat in ["kicking", "punting", "kickReturns", "puntReturns"]:
                    for p in st_side.get("specialTeams", {}).get(cat, []):
                        if p.get("foto") in mapa_cache:
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
            let cdnData = null, sumData = null, standData = null, playoffsData = [];
            try {
                let rCdn = await fetch(`https://cdn.espn.com/core/nfl/game?xhr=1&gameId=${gId}&t=${Date.now()}`, { cache: 'no-store' });
                if (rCdn.ok) {
                    let jCdn = await rCdn.json();
                    cdnData = jCdn.gamepackage || (jCdn.gmStrp ? jCdn : null);
                }
            } catch(e) {}
            try {
                let r = await fetch(`https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event=${gId}&t=${Date.now()}`, { cache: 'no-store' });
                if (r.ok) sumData = await r.json();
            } catch(e) {}
            try {
                let rS = await fetch(`https://site.api.espn.com/apis/v2/sports/football/nfl/standings?level=3&t=${Date.now()}`, { cache: 'no-store' });
                if (rS.ok) standData = await rS.json();
            } catch(e) {}

            try {
                let ano = sumData?.header?.season?.year || cdnData?.gmStrp?.season?.year || new Date().getFullYear();
                let semanasPlayoffs = [1, 2, 3, 5];
                let fetches = semanasPlayoffs.map(sem =>
                    fetch(`https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates=${ano}&seasontype=3&week=${sem}&t=${Date.now()}`, { cache: 'no-store' })
                        .then(r => r.ok ? r.json() : null)
                        .catch(() => null)
                );
                playoffsData = await Promise.all(fetches);
            } catch(e) {}

            return { cdn: cdnData, summary: sumData, standings: standData, playoffs: playoffsData };
        }
        obterDadosNFL().then(res => done(res)).catch(() => done(null));
        """
        
        resp = driver.execute_async_script(script_extracao, game_id)
        if not resp: return None

        cdn_data = resp.get('cdn') or {}
        data = resp.get('summary') or cdn_data
        stand_data = resp.get('standings') or {}
        playoffs_resp = resp.get('playoffs') or []
        if not data: return None

        if not stand_data or not stand_data.get('children'):
            try:
                r_py = requests.get("https://site.api.espn.com/apis/v2/sports/football/nfl/standings?level=3", timeout=3)
                if r_py.ok: stand_data = r_py.json()
            except Exception: pass

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
        
        cor_hex_fora = t_away.get('color', '0085ca')
        cor_fora = f"#{cor_hex_fora}" if not cor_hex_fora.startswith('#') else cor_hex_fora

        record_fora = ""
        for rec in away_team.get('records', []):
            if rec.get('type') in ['total', 'overall', '']:
                record_fora = rec.get('summary', '')
                break
        if not record_fora and away_team.get('records'):
            record_fora = away_team['records'][0].get('summary', '')

        time_casa = t_home.get('shortDisplayName') or t_home.get('displayName') or t_home.get('abbreviation', 'Casa')
        logo_casa = (t_home.get('logos') or [{}])[0].get('href', '') if t_home.get('logos') else t_home.get('logo', '')
        abbrev_casa = t_home.get('abbreviation', '')
        id_casa = str(t_home.get('id') or home_team.get('id', ''))
        placar_casa = str(home_team.get('score', '0'))
        
        cor_hex_casa = t_home.get('color', '203731')
        cor_casa = f"#{cor_hex_casa}" if not cor_hex_casa.startswith('#') else cor_hex_casa

        record_casa = ""
        for rec in home_team.get('records', []):
            if rec.get('type') in ['total', 'overall', '']:
                record_casa = rec.get('summary', '')
                break
        if not record_casa and home_team.get('records'):
            record_casa = home_team['records'][0].get('summary', '')

        st_obj = comps.get('status', {})
        st_type = st_obj.get('type', {})
        state = st_type.get('state', 'in')
        tempo_det = st_type.get('detail', '')
        tempo_desc = st_type.get('description', '')
        display_clock = st_obj.get('displayClock', '')
        period = st_obj.get('period', 0)

        is_pre_jogo = (state == 'pre')
        if is_pre_jogo:
            placar_fora, placar_casa = "-", "-"
            tempo = "EM BREVE"
        elif state == 'post':
            tempo = "FINALIZADO"
            placar_fora = str(away_team.get('score', '-'))
            placar_casa = str(home_team.get('score', '-'))
        else:
            if 'halftime' in tempo_desc.lower() or 'intervalo' in tempo_det.lower():
                tempo = "INTERVALO"
            elif display_clock == "0:00" and period in [1, 3]:
                tempo = f"FIM DO {period}º QUARTO"
            else:
                periodo_txt = f"{period}º QUARTO" if 1 <= period <= 4 else ("OVERTIME" if period > 4 else "AO VIVO")
                tempo = f"{display_clock} - {periodo_txt}" if display_clock else periodo_txt

        venue_obj = data.get('gameInfo', {}).get('venue', {})
        nome_estadio = venue_obj.get('fullName', '')
        cidade_estadio = venue_obj.get('address', {}).get('city', '')
        estado_estadio = venue_obj.get('address', {}).get('state', '')
        local_completo = f"{nome_estadio} {cidade_estadio}, {estado_estadio}".strip(", ")

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

        def extrair_atleta(entry, cat_nome):
            if not entry: return None
            ath = entry.get('athlete', {})
            if not ath: return None
            foto = ""
            if isinstance(ath.get('headshot'), dict): foto = ath.get('headshot', {}).get('href', '')
            elif isinstance(ath.get('headshot'), str): foto = ath.get('headshot', '')
            if 'nophoto' in foto: foto = ''
            pos = ath.get('position', {})
            pos_str = pos.get('abbreviation', '') if isinstance(pos, dict) else str(pos or '')
            raw_val = str(entry.get('displayValue', '-'))
            st_val, det_val = separar_stat_e_detalhe(cat_nome, raw_val)
            return {
                "nome": ath.get('shortName') or ath.get('displayName', ''),
                "posicao": pos_str,
                "detalhe": det_val,
                "stat": st_val,
                "foto": foto
            }

        lideres_formatados = []
        gmLdrs = cdn_data.get('gmLdrs', {}) if isinstance(cdn_data, dict) else {}
        if gmLdrs and gmLdrs.get('ldrs'):
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
                        "nome": p.get('nameShort', ''),
                        "posicao": p.get('position', ''),
                        "detalhe": p.get('stats', ''),
                        "stat": str(p.get('primaryStatValue', '-')),
                        "foto": foto
                    }
                lideres_formatados.append({
                    "categoria": cat_label,
                    "away": extrair_p(p_away),
                    "home": extrair_p(p_home)
                })

        if not lideres_formatados:
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
                        if cat_key not in categorias_map:
                            categorias_map[cat_key] = {"categoria": cat_label, "away": None, "home": None}
                        top_entry = (cat.get('leaders') or [{}])[0]
                        atleta = extrair_atleta(top_entry, cat_name)
                        if is_away: categorias_map[cat_key]["away"] = atleta
                        else: categorias_map[cat_key]["home"] = atleta

                elif 'name' in item and 'leaders' in item:
                    cat_name = item.get('name', '').lower()
                    cat_label = trans_cat.get(cat_name) or item.get('displayName', '')
                    cat_key = cat_name or cat_label
                    if cat_key not in categorias_map:
                        categorias_map[cat_key] = {"categoria": cat_label, "away": None, "home": None}

                    for ldr_entry in item.get('leaders', []):
                        t_info = ldr_entry.get('team', {}) or ldr_entry.get('athlete', {}).get('team', {})
                        t_abbr = str(t_info.get('abbreviation', '')).upper()
                        t_id = str(t_info.get('id', ''))
                        is_away = (t_abbr == abbrev_fora.upper() or (t_id and t_id == id_fora))
                        atleta = extrair_atleta(ldr_entry, cat_name)
                        if is_away: categorias_map[cat_key]["away"] = atleta
                        else: categorias_map[cat_key]["home"] = atleta

            lideres_formatados = list(categorias_map.values())

        def extrair_quartos(comp_team):
            ls = comp_team.get('linescores', [])
            quartos = []
            for q in ls:
                if isinstance(q, dict):
                    v = q.get('displayValue')
                    if v is None or v == "": v = q.get('value')
                    quartos.append(str(int(float(v))) if v is not None and str(v).replace('.', '', 1).isdigit() else str(v or "0"))
                else: quartos.append(str(q))
            return quartos

        q_fora = extrair_quartos(away_team)
        q_casa = extrair_quartos(home_team)

        team_stats_raw = data.get('boxscore', {}).get('teams', [])
        stats_map = {"pass": {"away": 0, "home": 0}, "rush": {"away": 0, "home": 0}, "total": {"away": 0, "home": 0}}
        for tm in team_stats_raw:
            is_away = str(tm.get('team', {}).get('id', '')) == id_fora
            lado = "away" if is_away else "home"
            for st in tm.get('statistics', []):
                s_name = st.get('name', '').lower()
                val = int(st.get('displayValue', '0').replace(',', '')) if st.get('displayValue', '0').lstrip('-').isdigit() else 0
                if s_name in ["netpassingyards", "passingyards"]: stats_map["pass"][lado] = val
                elif s_name == "rushingyards": stats_map["rush"][lado] = val
                elif s_name == "totalyards": stats_map["total"][lado] = val

        barras_comparativas = [
            {"label": "PASS YDS", "away": stats_map["pass"]["away"], "home": stats_map["pass"]["home"]},
            {"label": "RUSH YDS", "away": stats_map["rush"]["away"], "home": stats_map["rush"]["home"]},
            {"label": "TOTAL YDS", "away": stats_map["total"]["away"], "home": stats_map["total"]["home"]}
        ]

        def extrair_categorias_time(team_id):
            offense = {"passing": [], "rushing": [], "receiving": []}
            defense = []
            special_teams = {"kicking": [], "punting": [], "kickReturns": [], "puntReturns": []}

            def obter_foto(ath):
                h = ath.get('headshot')
                if isinstance(h, dict): return h.get('href', '')
                return h if isinstance(h, str) else ''

            box_players = data.get('boxscore', {}).get('players', [])
            team_box = next((b for b in box_players if str(b.get('team', {}).get('id', '')) == str(team_id)), None)

            if team_box:
                for stat_grp in team_box.get('statistics', []):
                    cat = stat_grp.get('name', '').lower()
                    labels = [lbl.upper() for lbl in stat_grp.get('labels', [])]
                    athletes = stat_grp.get('athletes', [])

                    if cat == "passing":
                        idx_cp = labels.index('C/ATT') if 'C/ATT' in labels else 0
                        idx_yd = labels.index('YDS') if 'YDS' in labels else 1
                        idx_td = labels.index('TD') if 'TD' in labels else 3
                        idx_int = labels.index('INT') if 'INT' in labels else 4
                        for a in athletes:
                            st = a.get('stats', [])
                            if len(st) > max(idx_cp, idx_yd, idx_td, idx_int):
                                try: fpts = round(int(st[idx_yd]) * 0.04 + int(st[idx_td]) * 4 - int(st[idx_int]) * 2)
                                except Exception: fpts = 0
                                offense["passing"].append({
                                    "nome": a.get('athlete', {}).get('shortName') or a.get('athlete', {}).get('displayName', ''),
                                    "foto": obter_foto(a.get('athlete', {})),
                                    "cp_att": st[idx_cp], "yds": st[idx_yd], "td": st[idx_td], "int": st[idx_int], "fpts": fpts
                                })

                    elif cat == "rushing":
                        idx_att = labels.index('CAR') if 'CAR' in labels else (labels.index('ATT') if 'ATT' in labels else 0)
                        idx_yd = labels.index('YDS') if 'YDS' in labels else 1
                        idx_td = labels.index('TD') if 'TD' in labels else 3
                        idx_long = labels.index('LONG') if 'LONG' in labels else (labels.index('LG') if 'LG' in labels else 4)
                        for a in athletes:
                            st = a.get('stats', [])
                            if len(st) > max(idx_att, idx_yd, idx_td, idx_long):
                                try: fpts = round(int(st[idx_yd]) * 0.1 + int(st[idx_td]) * 6)
                                except Exception: fpts = 0
                                offense["rushing"].append({
                                    "nome": a.get('athlete', {}).get('shortName') or a.get('athlete', {}).get('displayName', ''),
                                    "foto": obter_foto(a.get('athlete', {})),
                                    "att": st[idx_att], "yds": st[idx_yd], "td": st[idx_td], "long": st[idx_long], "fpts": fpts
                                })

                    elif cat == "receiving":
                        idx_rec = labels.index('REC') if 'REC' in labels else 0
                        idx_yd = labels.index('YDS') if 'YDS' in labels else 1
                        idx_td = labels.index('TD') if 'TD' in labels else 3
                        idx_long = labels.index('LONG') if 'LONG' in labels else (labels.index('LG') if 'LG' in labels else 4)
                        idx_tar = labels.index('TGTS') if 'TGTS' in labels else (labels.index('TAR') if 'TAR' in labels else 5)
                        for a in athletes:
                            st = a.get('stats', [])
                            if len(st) > max(idx_rec, idx_yd, idx_td, idx_long):
                                tar_val = st[idx_tar] if len(st) > idx_tar else st[idx_rec]
                                try: fpts = round(int(st[idx_yd]) * 0.1 + int(st[idx_td]) * 6 + int(st[idx_rec]) * 1)
                                except Exception: fpts = 0
                                offense["receiving"].append({
                                    "nome": a.get('athlete', {}).get('shortName') or a.get('athlete', {}).get('displayName', ''),
                                    "foto": obter_foto(a.get('athlete', {})),
                                    "tar": tar_val, "rec": st[idx_rec], "yds": st[idx_yd], "td": st[idx_td], "long": st[idx_long], "fpts": fpts
                                })

                    elif cat in ["defensive", "defense"]:
                        idx_tot = labels.index('TOT') if 'TOT' in labels else 0
                        idx_solo = labels.index('SOLO') if 'SOLO' in labels else 1
                        idx_sacks = labels.index('SACKS') if 'SACKS' in labels else 2
                        idx_int = labels.index('INT') if 'INT' in labels else 4
                        idx_ff = labels.index('FF') if 'FF' in labels else (labels.index('PD') if 'PD' in labels else 5)
                        for a in athletes:
                            st = a.get('stats', [])
                            if len(st) > max(idx_tot, idx_solo, idx_sacks):
                                tot = int(st[idx_tot]) if str(st[idx_tot]).isdigit() else 0
                                solo = int(st[idx_solo]) if str(st[idx_solo]).isdigit() else 0
                                defense.append({
                                    "nome": a.get('athlete', {}).get('shortName') or a.get('athlete', {}).get('displayName', ''),
                                    "foto": obter_foto(a.get('athlete', {})),
                                    "t_a": f"{solo}-{max(0, tot - solo)}",
                                    "sack": st[idx_sacks],
                                    "int": st[idx_int] if len(st) > idx_int else "0",
                                    "ff": st[idx_ff] if len(st) > idx_ff else "0"
                                })

                    elif cat == "kicking":
                        idx_fg = labels.index('FG') if 'FG' in labels else 0
                        idx_long = labels.index('LONG') if 'LONG' in labels else (labels.index('LG') if 'LG' in labels else 2)
                        idx_xp = labels.index('XP') if 'XP' in labels else 3
                        idx_pts = labels.index('PTS') if 'PTS' in labels else 4
                        for a in athletes:
                            st = a.get('stats', [])
                            if len(st) > max(idx_fg, idx_long, idx_xp, idx_pts):
                                special_teams["kicking"].append({
                                    "nome": a.get('athlete', {}).get('shortName') or a.get('athlete', {}).get('displayName', ''),
                                    "foto": obter_foto(a.get('athlete', {})),
                                    "fg": st[idx_fg], "lg": st[idx_long], "xp": st[idx_xp], "pts": st[idx_pts]
                                })

                    elif cat == "punting":
                        idx_no = labels.index('NO') if 'NO' in labels else 0
                        idx_avg = labels.index('AVG') if 'AVG' in labels else 2
                        idx_in20 = labels.index('IN 20') if 'IN 20' in labels else (labels.index('IN20') if 'IN20' in labels else 4)
                        idx_long = labels.index('LONG') if 'LONG' in labels else (labels.index('LG') if 'LG' in labels else 5)
                        for a in athletes:
                            st = a.get('stats', [])
                            if len(st) > max(idx_no, idx_avg):
                                special_teams["punting"].append({
                                    "nome": a.get('athlete', {}).get('shortName') or a.get('athlete', {}).get('displayName', ''),
                                    "foto": obter_foto(a.get('athlete', {})),
                                    "no": st[idx_no], "avg": st[idx_avg],
                                    "in20": st[idx_in20] if len(st) > idx_in20 else "0",
                                    "lg": st[idx_long] if len(st) > idx_long else "0"
                                })

                    elif cat in ["kickreturns", "kick_returns"]:
                        idx_no = labels.index('NO') if 'NO' in labels else 0
                        idx_avg = labels.index('AVG') if 'AVG' in labels else 2
                        idx_long = labels.index('LONG') if 'LONG' in labels else 3
                        idx_td = labels.index('TD') if 'TD' in labels else 4
                        for a in athletes:
                            st = a.get('stats', [])
                            if len(st) > max(idx_no, idx_avg):
                                special_teams["kickReturns"].append({
                                    "nome": a.get('athlete', {}).get('shortName') or a.get('athlete', {}).get('displayName', ''),
                                    "foto": obter_foto(a.get('athlete', {})),
                                    "no": st[idx_no], "avg": st[idx_avg],
                                    "lg": st[idx_long] if len(st) > idx_long else "0",
                                    "td": st[idx_td] if len(st) > idx_td else "0"
                                })

                    elif cat in ["puntreturns", "punt_returns"]:
                        idx_no = labels.index('NO') if 'NO' in labels else 0
                        idx_avg = labels.index('AVG') if 'AVG' in labels else 2
                        idx_long = labels.index('LONG') if 'LONG' in labels else 3
                        idx_td = labels.index('TD') if 'TD' in labels else 4
                        for a in athletes:
                            st = a.get('stats', [])
                            if len(st) > max(idx_no, idx_avg):
                                special_teams["puntReturns"].append({
                                    "nome": a.get('athlete', {}).get('shortName') or a.get('athlete', {}).get('displayName', ''),
                                    "foto": obter_foto(a.get('athlete', {})),
                                    "no": st[idx_no], "avg": st[idx_avg],
                                    "lg": st[idx_long] if len(st) > idx_long else "0",
                                    "td": st[idx_td] if len(st) > idx_td else "0"
                                })

            return {"offense": offense, "defense": defense, "specialTeams": special_teams}

        cbs_data = {
            "venue": local_completo,
            "corAway": cor_fora,
            "corHome": cor_casa,
            "away": {"nome": time_fora, "record": record_fora, "logo": logo_fora, "quartos": q_fora, "total": placar_fora},
            "home": {"nome": time_casa, "record": record_casa, "logo": logo_casa, "quartos": q_casa, "total": placar_casa},
            "barras": barras_comparativas,
            "away_stats": extrair_categorias_time(id_fora),
            "home_stats": extrair_categorias_time(id_casa)
        }

        tabelas_grupos_nfl = []

        def abreviar_divisao_nfl(texto_bruto):
            t = (texto_bruto or "").upper()
            conf = "AFC" if ("AFC" in t or "AMERICAN" in t) else ("NFC" if ("NFC" in t or "NATIONAL" in t) else "")
            
            div = ""
            if "EAST" in t or "LESTE" in t: div = "Leste"
            elif "NORTH" in t or "NORTE" in t: div = "Norte"
            elif "SOUTH" in t or "SUL" in t: div = "Sul"
            elif "WEST" in t or "OESTE" in t: div = "Oeste"

            if conf and div:
                return f"{conf} {div}"
            return texto_bruto.strip()

        def coletar_divisoes_recursivo(obj, prefixo=""):
            if not obj: return
            if isinstance(obj, dict):
                nome_atual = obj.get('name') or obj.get('abbreviation') or ""
                entries = obj.get('standings', {}).get('entries', [])
                if entries and isinstance(entries, list):
                    rotulo_bruto = f"{prefixo} {nome_atual}".strip()
                    rotulo_div = abreviar_divisao_nfl(rotulo_bruto)
                    
                    linhas = []
                    for idx, e in enumerate(entries):
                        tm = e.get('team', {})
                        t_id = str(tm.get('id', ''))
                        st_dict = {str(s.get('name', '')).lower(): s.get('displayValue', str(s.get('value', '0'))) for s in e.get('stats', [])}
                        
                        try: v = int(st_dict.get('wins', 0))
                        except: v = 0
                        try: d = int(st_dict.get('losses', 0))
                        except: d = 0
                        try: emp = int(st_dict.get('ties', 0))
                        except: emp = 0
                        
                        pct_raw = st_dict.get('winpercent') or st_dict.get('pct') or "0"
                        try:
                            fp = float(pct_raw)
                            pct_fmt = f"{fp:.3f}".lstrip("0") if fp < 1.0 else ("1.000" if fp == 1.0 else f"{fp:.1f}%")
                        except: pct_fmt = str(pct_raw)
                        
                        diff_val = st_dict.get('pointdifferential') or st_dict.get('differential') or "0"
                        if not str(diff_val).startswith('+') and not str(diff_val).startswith('-') and str(diff_val) != '0':
                            diff_val = f"+{diff_val}"
                            
                        logo_t = ""
                        if tm.get('logos'): logo_t = tm['logos'][0].get('href', '')
                        elif tm.get('logo'): logo_t = tm.get('logo', '')
                        
                        linhas.append({
                            "pos": idx + 1,
                            "variacao": 0,
                            "id": t_id,
                            "nome": tm.get('displayName') or tm.get('shortDisplayName') or tm.get('name') or "Time",
                            "promocao": "Playoffs" if idx == 0 else "",
                            "logo": logo_t,
                            "jogos": v + d + emp,
                            "v": v,
                            "e": emp,
                            "d": d,
                            "sg": str(diff_val),
                            "pts": "-",
                            "pct": pct_fmt,
                            "isCasa": str(t_id) == str(id_casa),
                            "isFora": str(t_id) == str(id_fora)
                        })
                    
                    tem_jogo = any(t["isCasa"] or t["isFora"] for t in linhas)
                    tabelas_grupos_nfl.append({
                        "grupo": rotulo_div,
                        "ativoPadrao": tem_jogo,
                        "times": linhas
                    })
                    return

                for k in ['children', 'standings']:
                    if k in obj:
                        coletar_divisoes_recursivo(obj[k], nome_atual if not prefixo else f"{prefixo} {nome_atual}")
            elif isinstance(obj, list):
                for item in obj:
                    coletar_divisoes_recursivo(item, prefixo)

        coletar_divisoes_recursivo(stand_data)

        times_afc = []
        times_nfc = []

        for g in tabelas_grupos_nfl:
            nome_g = g.get("grupo", "").upper()
            for t in g.get("times", []):
                t_copia = dict(t)
                if "AFC" in nome_g:
                    times_afc.append(t_copia)
                elif "NFC" in nome_g:
                    times_nfc.append(t_copia)

        def ordenar_conferencia(lista_times):
            def chave_ord(tm):
                try: p = float(tm.get("pct", 0))
                except: p = 0.0
                try: s = int(str(tm.get("sg", 0)).replace("+", ""))
                except: s = 0
                return (p, s)

            lista_ordenada = sorted(lista_times, key=chave_ord, reverse=True)
            for idx, tm in enumerate(lista_ordenada):
                pos = idx + 1
                tm["pos"] = pos
                if pos == 1:
                    tm["promocao"] = "Playoffs (Folga #1)"
                elif pos <= 7:
                    tm["promocao"] = "Playoffs (Wild Card)"
                else:
                    tm["promocao"] = ""
            return lista_ordenada

        grupos_gerais = []
        afc_ordenada = []
        nfc_ordenada = []
        if times_afc:
            afc_ordenada = ordenar_conferencia(times_afc)
            tem_jogo_afc = any(t["isCasa"] or t["isFora"] for t in afc_ordenada)
            grupos_gerais.append({
                "grupo": "AFC (Geral)",
                "ativoPadrao": tem_jogo_afc,
                "times": afc_ordenada
            })

        if times_nfc:
            nfc_ordenada = ordenar_conferencia(times_nfc)
            tem_jogo_nfc = any(t["isCasa"] or t["isFora"] for t in nfc_ordenada)
            grupos_gerais.append({
                "grupo": "NFC (Geral)",
                "ativoPadrao": tem_jogo_nfc and (not times_afc or not tem_jogo_afc),
                "times": nfc_ordenada
            })

        tabelas_grupos_nfl = grupos_gerais + tabelas_grupos_nfl

        matamata_nfl = []

        nomes_fases_espn = {
            1: "Rodada de Wild Card",
            2: "Rodada Divisional",
            3: "Finais de Conferência",
            5: "Super Bowl (Grande Final)"
        }

        for sem_idx, sem_json in enumerate(playoffs_resp):
            if not isinstance(sem_json, dict): continue
            events = sem_json.get('events', [])
            if not events: continue

            num_sem = sem_json.get('week', {}).get('number') or [1, 2, 3, 5][sem_idx]
            nome_fase = nomes_fases_espn.get(num_sem, f"Playoffs - Rodada {num_sem}")

            jogos_fase = []
            for ev in events:
                comp = (ev.get('competitions') or [{}])[0]
                competitors = comp.get('competitors', [])
                if len(competitors) < 2: continue

                ev_name = ev.get('name', '').lower()
                notes = comp.get('notes', [])
                headline = notes[0].get('headline', '') if notes else ''
                if 'pro bowl' in ev_name or 'pro bowl' in headline.lower(): continue

                h_comp = next((c for c in competitors if c.get('homeAway') == 'home'), competitors[0])
                a_comp = next((c for c in competitors if c.get('homeAway') == 'away'), competitors[1])

                t_home = h_comp.get('team', {})
                t_away = a_comp.get('team', {})

                h_score = str(h_comp.get('score', '-'))
                a_score = str(a_comp.get('score', '-'))

                h_name = t_home.get('displayName') or t_home.get('shortDisplayName') or 'Casa'
                a_name = t_away.get('displayName') or t_away.get('shortDisplayName') or 'Fora'

                h_seed = h_comp.get('curatedRank', {}).get('current')
                a_seed = a_comp.get('curatedRank', {}).get('current')
                if h_seed and 1 <= h_seed <= 7: h_name = f"#{h_seed} {h_name}"
                if a_seed and 1 <= a_seed <= 7: a_name = f"#{a_seed} {a_name}"

                h_logo = (t_home.get('logos') or [{}])[0].get('href', '') if t_home.get('logos') else t_home.get('logo', '')
                a_logo = (t_away.get('logos') or [{}])[0].get('href', '') if t_away.get('logos') else t_away.get('logo', '')

                st_desc = comp.get('status', {}).get('type', {}).get('detail', 'Final')
                if headline and any(k in headline.lower() for k in ['afc', 'nfc', 'super bowl']):
                    status_card = f"{headline} • {st_desc}"
                else:
                    status_card = st_desc

                h_id = str(t_home.get('id', ''))
                a_id = str(t_away.get('id', ''))
                is_jogo_atual = (h_id in [str(id_casa), str(id_fora)]) or (a_id in [str(id_casa), str(id_fora)])

                jogos_fase.append({
                    "time1": a_name,
                    "logo1": a_logo,
                    "placar1": a_score,
                    "time2": h_name,
                    "logo2": h_logo,
                    "placar2": h_score,
                    "status": status_card,
                    "isJogoAtual": is_jogo_atual
                })

            if jogos_fase:
                matamata_nfl.append({
                    "fase": nome_fase,
                    "jogos": jogos_fase
                })

        if not matamata_nfl and len(afc_ordenada) >= 7 and len(nfc_ordenada) >= 7:
            a1, a2, a3, a4, a5, a6, a7 = afc_ordenada[:7]
            n1, n2, n3, n4, n5, n6, n7 = nfc_ordenada[:7]

            jogos_wc_afc = [
                {
                    "time1": f"#{a1['pos']} {a1['nome']}", "logo1": a1['logo'], "placar1": "BYE",
                    "time2": "Aguardando Vencedor", "logo2": "", "placar2": "-",
                    "status": f"Folga na 1ª Rodada • ({a1.get('v',0)}-{a1.get('d',0)})",
                    "isJogoAtual": (str(a1['id']) in [str(id_casa), str(id_fora)])
                },
                {
                    "time1": f"#{a2['pos']} {a2['nome']}", "logo1": a2['logo'], "placar1": f"{a2.get('v',0)}-{a2.get('d',0)}",
                    "time2": f"#{a7['pos']} {a7['nome']}", "logo2": a7['logo'], "placar2": f"{a7.get('v',0)}-{a7.get('d',0)}",
                    "status": "Wild Card • Seed #2 vs #7",
                    "isJogoAtual": (str(a2['id']) in [str(id_casa), str(id_fora)]) or (str(a7['id']) in [str(id_casa), str(id_fora)])
                },
                {
                    "time1": f"#{a3['pos']} {a3['nome']}", "logo1": a3['logo'], "placar1": f"{a3.get('v',0)}-{a3.get('d',0)}",
                    "time2": f"#{a6['pos']} {a6['nome']}", "logo2": a6['logo'], "placar2": f"{a6.get('v',0)}-{a6.get('d',0)}",
                    "status": "Wild Card • Seed #3 vs #6",
                    "isJogoAtual": (str(a3['id']) in [str(id_casa), str(id_fora)]) or (str(a6['id']) in [str(id_casa), str(id_fora)])
                },
                {
                    "time1": f"#{a4['pos']} {a4['nome']}", "logo1": a4['logo'], "placar1": f"{a4.get('v',0)}-{a4.get('d',0)}",
                    "time2": f"#{a5['pos']} {a5['nome']}", "logo2": a5['logo'], "placar2": f"{a5.get('v',0)}-{a5.get('d',0)}",
                    "status": "Wild Card • Seed #4 vs #5",
                    "isJogoAtual": (str(a4['id']) in [str(id_casa), str(id_fora)]) or (str(a5['id']) in [str(id_casa), str(id_fora)])
                }
            ]

            jogos_wc_nfc = [
                {
                    "time1": f"#{n1['pos']} {n1['nome']}", "logo1": n1['logo'], "placar1": "BYE",
                    "time2": "Aguardando Vencedor", "logo2": "", "placar2": "-",
                    "status": f"Folga na 1ª Rodada • ({n1.get('v',0)}-{n1.get('d',0)})",
                    "isJogoAtual": (str(n1['id']) in [str(id_casa), str(id_fora)])
                },
                {
                    "time1": f"#{n2['pos']} {n2['nome']}", "logo1": n2['logo'], "placar1": f"{n2.get('v',0)}-{n2.get('d',0)}",
                    "time2": f"#{n7['pos']} {n7['nome']}", "logo2": n7['logo'], "placar2": f"{n7.get('v',0)}-{n7.get('d',0)}",
                    "status": "Wild Card • Seed #2 vs #7",
                    "isJogoAtual": (str(n2['id']) in [str(id_casa), str(id_fora)]) or (str(n7['id']) in [str(id_casa), str(id_fora)])
                },
                {
                    "time1": f"#{n3['pos']} {n3['nome']}", "logo1": n3['logo'], "placar1": f"{n3.get('v',0)}-{n3.get('d',0)}",
                    "time2": f"#{n6['pos']} {n6['nome']}", "logo2": n6['logo'], "placar2": f"{n6.get('v',0)}-{n6.get('d',0)}",
                    "status": "Wild Card • Seed #3 vs #6",
                    "isJogoAtual": (str(n3['id']) in [str(id_casa), str(id_fora)]) or (str(n6['id']) in [str(id_casa), str(id_fora)])
                },
                {
                    "time1": f"#{n4['pos']} {n4['nome']}", "logo1": n4['logo'], "placar1": f"{n4.get('v',0)}-{n4.get('d',0)}",
                    "time2": f"#{n5['pos']} {n5['nome']}", "logo2": n5['logo'], "placar2": f"{n5.get('v',0)}-{n5.get('d',0)}",
                    "status": "Wild Card • Seed #4 vs #5",
                    "isJogoAtual": (str(n4['id']) in [str(id_casa), str(id_fora)]) or (str(n5['id']) in [str(id_casa), str(id_fora)])
                }
            ]

            matamata_nfl.append({"fase": "AFC • Rodada de Wild Card", "jogos": jogos_wc_afc})
            matamata_nfl.append({"fase": "NFC • Rodada de Wild Card", "jogos": jogos_wc_nfc})

        grupo_principal = next((g for g in tabelas_grupos_nfl if g["ativoPadrao"]), None)
        if not grupo_principal and tabelas_grupos_nfl:
            grupo_principal = tabelas_grupos_nfl[0]
        tabela_classificacao = grupo_principal["times"] if grupo_principal else []

        return {
            "esporte": "nfl", "timeCasa": time_casa, "logoCasa": logo_casa, "abbrevCasa": abbrev_casa,
            "placarCasa": placar_casa, "timeFora": time_fora, "logoFora": logo_fora, "abbrevFora": abbrev_fora,
            "placarFora": placar_fora, "tempo": tempo, "torneio": "NFL",
            "isPreJogo": is_pre_jogo,
            "titulo_destaques": "LÍDERES DA TEMPORADA" if is_pre_jogo else "LÍDERES DO JOGO",
            "lideres_nfl": lideres_formatados,
            "cbs_nfl": cbs_data,
            "grupos": tabelas_grupos_nfl,
            "tabela": tabela_classificacao,
            "matamata": matamata_nfl
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
    
    if "espn" in url_atual:
        dados_nfl = extrair_dados_espn_nfl()
        if dados_nfl:
            dados_final = cachear_todas_imagens(driver, [dados_nfl])
            with open('dados.json', 'w', encoding='utf-8') as f: 
                json.dump(dados_final, f, ensure_ascii=False, indent=4)
            return "nfl"
        return "futebol"
    
    if "formula1.com" in url_atual:
        global comando_f1_pendente, f1_url_cache
        if comando_f1_pendente:
            alvo = comando_f1_pendente
            comando_f1_pendente = None
            
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

        const mapaCodigosNac = {
            "gbr": "gb", "ita": "it", "mon": "mc", "ned": "nl", "fra": "fr", "aus": "au",
            "esp": "es", "tha": "th", "jpn": "jp", "ger": "de", "bra": "br", "arg": "ar",
            "fin": "fi", "can": "ca", "mex": "mx", "nzl": "nz", "chn": "cn", "den": "dk"
        };

        linhas.forEach(linha => {
            let colunas = linha.querySelectorAll('td');
            if (colunas.length >= 2) {
                let pos = colunas[posIdx] ? colunas[posIdx].innerText.trim() : "";

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

                let celulaEquipe = (teamIdx !== -1 && colunas[teamIdx]) ? colunas[teamIdx] : null;
                let equipe = celulaEquipe ? celulaEquipe.innerText.trim() : '';
                let imgLogo = celulaEquipe ? celulaEquipe.querySelector('img') : null;
                let logoUrl = imgLogo ? (imgLogo.src || imgLogo.dataset?.src || '') : '';
                let spanLogo = celulaEquipe ? celulaEquipe.querySelector('[style*="background-color"]') : null;
                let corEquipe = spanLogo ? spanLogo.style.backgroundColor : "transparent";

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
                # Verifica se a URL contém "brazil" ou "sao-paulo"
                is_brazil = "brazil" in url_atual or "sao-paulo" in url_atual
                
                f1_obj = {
                    "esporte": "f1",
                    "torneio": titulo_pagina,
                    "tempo": (sub_treino if sessao_ativa == "Treino" else sessao_ativa).upper(),
                    "estadio": "formula1.com",
                    "abaAtiva": sessao_ativa,
                    "subTreino": sub_treino,
                    "classificacaoF1": dados_tabela,
                    "isBrazil": is_brazil
                }
                dados_com_cache = cachear_todas_imagens(driver, [f1_obj])
                with open('dados.json', 'w', encoding='utf-8') as f: 
                    json.dump(dados_com_cache, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print("Erro F1:", e)
            
        return "f1"
    
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

        // 2. Mata-Mata / Cuptrees com fallbacks robustos para Copa do Brasil, Champions e Libertadores
        try {
            let resCup = null;
            if (uId && sId) {
                resCup = await fetch(`/api/v1/unique-tournament/${uId}/season/${sId}/cuptrees`).then(r => r.ok ? r.json() : null).catch(() => null);
            }
            if (!resCup && tId && sId) {
                resCup = await fetch(`/api/v1/tournament/${tId}/season/${sId}/cuptrees`).then(r => r.ok ? r.json() : null).catch(() => null);
            }
            if (!resCup && uId) {
                resCup = await fetch(`/api/v1/unique-tournament/${uId}/cuptrees`).then(r => r.ok ? r.json() : null).catch(() => null);
            }

            let trees = resCup?.cupTrees || resCup?.cupTree || [];
            let treeAlvo = null;
            if (Array.isArray(trees) && trees.length > 0) {
                treeAlvo = trees.find(t => {
                    let n = (t.name || "").toLowerCase();
                    return !n.includes("qualif") && !n.includes("prelimin") && !n.includes("pré-") && !n.includes("fase prévia");
                }) || trees[0];
            }

            let dTree = null;
            if (treeAlvo?.id) {
                let tid = treeAlvo.id;
                dTree = await fetch(`/api/v1/cup-tree/${tid}`).then(r => r.ok ? r.json() : null).catch(() => null);
            }

            let arvoreFinal = dTree || treeAlvo || resCup || {};
            let eventosDetalhados = {};

            function registrarEvento(evItem) {
                if (evItem && evItem.id && (evItem.homeScore !== undefined || evItem.status !== undefined || evItem.homeTeam !== undefined)) {
                    eventosDetalhados[String(evItem.id)] = evItem;
                }
            }

            if (Array.isArray(resCup?.events)) resCup.events.forEach(registrarEvento);
            if (Array.isArray(dTree?.events)) dTree.events.forEach(registrarEvento);

            // Coleta todas as fases da árvore
            let todasRodadas = [];
            function coletarRodadas(o) {
                if (!o || typeof o !== 'object') return;
                if (Array.isArray(o.rounds)) {
                    todasRodadas.push(...o.rounds);
                }
                for (let k of Object.keys(o)) {
                    if (k !== 'eventsMap' && typeof o[k] === 'object') coletarRodadas(o[k]);
                }
            }
            coletarRodadas(arvoreFinal);

            // PRIORIDADE TOTAL: Varre as fases DA FINAL PARA TRÁS (Final, Semis, Quartas, Oitavas...)
            let idsOrdenados = [];
            let idsVistos = new Set();

            function extrairIdsDeBloco(blk) {
                if (!blk) return;
                let evList = blk.events || blk.matches || [];
                if (Array.isArray(evList)) {
                    for (let item of evList) {
                        let id = (typeof item === 'number' || typeof item === 'string') ? item : item?.id;
                        if (id && !idsVistos.has(String(id))) {
                            idsVistos.add(String(id));
                            idsOrdenados.push(id);
                            if (typeof item === 'object' && item !== null && item.id) {
                                registrarEvento(item);
                            }
                        }
                    }
                }
            }

            for (let i = todasRodadas.length - 1; i >= 0; i--) {
                let rnd = todasRodadas[i];
                let blks = rnd.blocks || rnd.events || rnd.matches || [];
                if (Array.isArray(blks)) {
                    blks.forEach(extrairIdsDeBloco);
                }
            }

            // Garante que o jogo da transmissão atual é incluído com prioridade
            if (eventId && !idsVistos.has(String(eventId))) {
                idsOrdenados.unshift(eventId);
            }

            // Busca os eventos decisivos (Ida e Volta garantidas sem corte prematuro)
            let idsParaBuscar = idsOrdenados.filter(id => !eventosDetalhados[String(id)]).slice(0, 90);
            if (idsParaBuscar.length > 0) {
                let promessas = idsParaBuscar.map(id =>
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

        return {
            evento: rEvento || {}, lineups: rLineups || {}, incidents: rIncidents || {},
            standings: rStandings || {}, cuptrees: rCuptrees || {}, relogioDom: extrairRelogioDOM(),
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
                    chave_time = f"{match_id}_{nome_grp}_{t_id}"
                    if chave_time not in posicoes_iniciais_times and pos_atual is not None:
                        posicoes_iniciais_times[chave_time] = pos_atual
                    pos_base = posicoes_iniciais_times.get(chave_time, pos_atual)
                    variacao = 0
                    if pos_base is not None and pos_atual is not None:
                        variacao = pos_base - pos_atual
                    pct_raw = r.get("percentage")
                    pct_str = ""
                    if pct_raw is not None:
                        try:
                            f_pct = float(pct_raw)
                            pct_str = f"{f_pct:.3f}".lstrip("0") if f_pct <= 1.0 else f"{f_pct:.1f}%"
                        except Exception:
                            pct_str = str(pct_raw)

                    linhas_grp.append({
                        "pos": pos_atual, "variacao": variacao, "id": t_id,
                        "nome": tm.get("shortName") or tm.get("name", ""),
                        "promocao": promo_txt, "logo": f"https://api.sofascore.app/api/v1/team/{t_id}/image" if t_id else "",
                        "jogos": r.get("matches", 0), "v": r.get("wins", 0), "e": r.get("draws", 0),
                        "d": r.get("losses", 0), "sg": str(diff), "pts": r.get("points", 0),
                        "pct": pct_str, "isCasa": str(t_id) == str(id_casa), "isFora": str(t_id) == str(id_fora)
                    })
                
                tem_time_jogo = any(t["isCasa"] or t["isFora"] for t in linhas_grp)
                tabelas_grupos.append({ "grupo": nome_grp, "ativoPadrao": tem_time_jogo, "times": linhas_grp })
                
                # FILTRO NBA: Mantém apenas as Conferências e remove as Divisões
            if esporte == "basquete":
                grupos_conferencias = [
                    g for g in tabelas_grupos 
                    if any(c in g["grupo"].lower() for c in ["conferen", "conferên"])
                ]
                
                # Fallback caso a API não traga a palavra "conference" no título
                if not grupos_conferencias:
                    termos_divisoes = [
                        "atlantic", "central", "southeast", "northwest", "pacific", "southwest", 
                        "atlântico", "sudoeste", "noroeste", "divis"
                    ]
                    grupos_conferencias = [
                        g for g in tabelas_grupos 
                        if not any(d in g["grupo"].lower() for d in termos_divisoes)
                    ]

                if grupos_conferencias:
                    tabelas_grupos = grupos_conferencias

            grupo_principal = next((g for g in tabelas_grupos if g["ativoPadrao"]), None)
            if not grupo_principal and tabelas_grupos: grupo_principal = tabelas_grupos[0]
            if grupo_principal: tabela_classificacao = grupo_principal["times"]

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
                            if isinstance(v, (dict, list)): buscar_rounds_recursivo(v)
                        elif k != "eventsMap":
                            if isinstance(v, (dict, list)): buscar_rounds_recursivo(v)
                elif isinstance(obj, list):
                    for item in obj: buscar_rounds_recursivo(item)

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
                
                if p_h is None and ev.get("homePenaltyScore") is not None: p_h = ev.get("homePenaltyScore")
                if p_a is None and ev.get("awayPenaltyScore") is not None: p_a = ev.get("awayPenaltyScore")

                return extrair_num(p_h), extrair_num(p_a)

            for rnd in rounds_encontrados:
                if not isinstance(rnd, dict): continue
                nome_fase = rnd.get("description") or rnd.get("name") or rnd.get("slug") or "Eliminatória"
                nome_low = nome_fase.lower()
                if any(p in nome_low for p in ["qualif", "prelimin", "pré-", "fase prévia"]): continue

                # Normalização de nomes
                if any(p in nome_low for p in ["3rd", "third", "3º", "3°", "terceiro", "bronze"]):
                    nome_fase = "Disputa de 3º Lugar"
                elif "final" in nome_low and not any(p in nome_low for p in ["semi", "quarter", "quarta", "oitava", "1/"]):
                    nome_fase = "Grande Final"

                confrontos_principais = []
                confrontos_3lugar = []
                blocos = rnd.get("blocks") or rnd.get("events") or rnd.get("matches") or []

                for blk in blocos:
                    if not isinstance(blk, dict): continue


                confrontos = []
                blocos = rnd.get("blocks") or rnd.get("events") or rnd.get("matches") or []

                for blk in blocos:
                    if not isinstance(blk, dict): continue

                    raw_events = blk.get("events") or blk.get("matches") or []
                    eventos_internos = []
                    if isinstance(raw_events, list):
                        for item in raw_events:
                            if isinstance(item, dict): eventos_internos.append(item)
                            elif isinstance(item, (int, str)):
                                ev_key = str(item)
                                if ev_key in mapa_eventos: eventos_internos.append(mapa_eventos[ev_key])

                    eventos_internos.sort(key=lambda x: x.get("startTimestamp", 0) if isinstance(x, dict) else 0)

                    h_tm, a_tm = None, None
                    scores_parts_0, scores_parts_1 = None, None
                    pen_part_0, pen_part_1 = None, None

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

                    # Destaca confrontos de qualquer um dos times da transmissão
                    is_jogo_atual = False
                    ids_alvo = {str(id_casa), str(id_fora)} - {"", "None", None}
                    if (str(h_id) in ids_alvo) or (str(a_id) in ids_alvo):
                        is_jogo_atual = True
                    else:
                        tc_low, tf_low = str(time_casa).lower().strip(), str(time_fora).lower().strip()
                        n1_low, n2_low = str(nome1).lower().strip(), str(nome2).lower().strip()
                        tem_casa = len(tc_low) >= 3 and (tc_low in n1_low or n1_low in tc_low or tc_low in n2_low or n2_low in tc_low)
                        tem_fora = len(tf_low) >= 3 and (tf_low in n1_low or n1_low in tf_low or tf_low in n2_low or n2_low in tf_low)
                        if tem_casa or tem_fora: is_jogo_atual = True

                    pernas_textos = []
                    total_t1 = 0
                    total_t2 = 0
                    teve_jogo_resolvido = False
                    p1_pen = pen_part_0
                    p2_pen = pen_part_1

                    if esporte == "basquete":
                        sc1_b, sc2_b = None, None
                        if parts and len(parts) >= 2:
                            sc1_b = extrair_num(parts[0].get("score") if isinstance(parts[0], dict) else None)
                            sc2_b = extrair_num(parts[1].get("score") if isinstance(parts[1], dict) else None)
                        
                        if sc1_b is not None and sc2_b is not None:
                            total_t1, total_t2 = sc1_b, sc2_b
                            teve_jogo_resolvido = True
                            if len(eventos_internos) > 0: pernas_textos.append(f"Série ({sc1_b}-{sc2_b})")

                    elif esporte == "futebol":
                        # 1. PROCESSAMENTO DE IDA E VOLTA VIA EVENTOS REAIS
                        if len(eventos_internos) > 0:
                            for idx, ev in enumerate(eventos_internos[:2]):
                                rotulo = "Ida" if idx == 0 else "Volta"
                                ev_hid = str(ev.get("homeTeam", {}).get("id", ""))
                                ev_hn = str(ev.get("homeTeam", {}).get("name", "")).lower()

                                # Identifica se o mandante deste jogo é o Time 1 do confronto
                                is_t1_casa = (ev_hid == str(h_id)) or (len(nome1) >= 3 and nome1.lower() in ev_hn)

                                sc_h = extrair_num(ev.get("homeScore"))
                                sc_a = extrair_num(ev.get("awayScore"))

                                pen_h, pen_a = extrair_penaltis_evento(ev)
                                if pen_h is not None and pen_a is not None:
                                    p1_pen = pen_h if is_t1_casa else pen_a
                                    p2_pen = pen_a if is_t1_casa else pen_h

                                if sc_h is not None and sc_a is not None:
                                    g_t1 = sc_h if is_t1_casa else sc_a
                                    g_t2 = sc_a if is_t1_casa else sc_h
                                    total_t1 += g_t1
                                    total_t2 += g_t2
                                    pernas_textos.append(f"{rotulo}: {g_t1}-{g_t2}")
                                    teve_jogo_resolvido = True
                                else:
                                    st_desc = obter_status_texto(ev)
                                    if not st_desc or st_desc.lower() in ["not started", "em breve", "a definir"]:
                                        pernas_textos.append(f"{rotulo}: EM BREVE")
                                    else:
                                        pernas_textos.append(f"{rotulo}: {st_desc}")

                            # Se o confronto prevê 2 jogos e apenas a Ida foi disputada
                            if len(raw_events) >= 2 and len(eventos_internos) == 1 and len(pernas_textos) == 1:
                                pernas_textos.append("Volta: EM BREVE")

                        # 2. FALLBACK VIA SCORES EM PARTICIPANTS
                        elif scores_parts_0 and scores_parts_1:
                            s0_ida = scores_parts_0[0] if len(scores_parts_0) > 0 else None
                            s1_ida = scores_parts_1[0] if len(scores_parts_1) > 0 else None
                            s0_volta = scores_parts_0[1] if len(scores_parts_0) > 1 else None
                            s1_volta = scores_parts_1[1] if len(scores_parts_1) > 1 else None

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
                            elif len(scores_parts_0) == 1:
                                pernas_textos.append("Volta: EM BREVE")

                    if not teve_jogo_resolvido:
                        raw_h, raw_a = None, None
                        if parts and len(parts) >= 2:
                            p0, p1 = parts[0], parts[1]
                            if isinstance(p0, dict) and isinstance(p1, dict):
                                for k in ["score", "aggregatedScore", "aggregateScore", "goals", "points", "value"]:
                                    if raw_h is None and p0.get(k) is not None: raw_h = p0.get(k)
                                    if raw_a is None and p1.get(k) is not None: raw_a = p1.get(k)
                        if raw_h is None or raw_a is None:
                            for kh, ka in [("aggregatedHomeScore", "aggregatedAwayScore"), ("aggregateHomeScore", "aggregateAwayScore"), ("homeTeamScore", "awayTeamScore"), ("homeScore", "awayScore"), ("score1", "score2")]:
                                if raw_h is None and blk.get(kh) is not None: raw_h = blk.get(kh)
                                if raw_a is None and blk.get(ka) is not None: raw_a = blk.get(ka)
                        h_num = extrair_num(raw_h)
                        a_num = extrair_num(raw_a)
                        if h_num is not None and a_num is not None:
                            placar1_final, placar2_final = str(h_num), str(a_num)
                            teve_jogo_resolvido = True
                        else:
                            placar1_final, placar2_final = "-", "-"
                    else:
                        placar1_final, placar2_final = str(total_t1), str(total_t2)

                    penaltis_str = f" (Pên: {p1_pen}-{p2_pen})" if (p1_pen is not None and p2_pen is not None) else ""
                    if len(pernas_textos) > 0: status_final = " • ".join(pernas_textos) + penaltis_str
                    else:
                        base_st = obter_status_texto(blk)
                        if not base_st: base_st = "FIM" if (teve_jogo_resolvido and placar1_final != "-") else "EM BREVE"
                        status_final = (base_st + penaltis_str).strip()

                    card_confronto = {
                        "time1": nome1, "logo1": f"https://api.sofascore.app/api/v1/team/{h_id}/image" if h_id else "",
                        "placar1": placar1_final, "pen1": str(p1_pen) if p1_pen is not None else None,
                        "time2": nome2, "logo2": f"https://api.sofascore.app/api/v1/team/{a_id}/image" if a_id else "",
                        "placar2": placar2_final, "pen2": str(p2_pen) if p2_pen is not None else None,
                        "status": status_final, "isJogoAtual": is_jogo_atual
                    }

                    # DETECTA SE ESTE CONFRONTO ESPECÍFICO É A DISPUTA DE 3º LUGAR
                    palavras_3lugar = ["3rd", "third", "3º", "3°", "terceiro", "bronze"]
                    b_txt = f"{blk.get('description', '')} {blk.get('name', '')} {blk.get('slug', '')}".lower()
                    is_3lugar = any(p in b_txt for p in palavras_3lugar)

                    if not is_3lugar and eventos_internos:
                        for ev_it in eventos_internos:
                            if isinstance(ev_it, dict):
                                r_info = ev_it.get('roundInfo', {})
                                r_name = str(r_info.get('name', '') if isinstance(r_info, dict) else '').lower()
                                ev_desc = str(ev_it.get('description', '')).lower()
                                if any(p in f"{r_name} {ev_desc}" for p in palavras_3lugar):
                                    is_3lugar = True
                                    break

                    if is_3lugar:
                        confrontos_3lugar.append(card_confronto)
                    else:
                        confrontos_principais.append(card_confronto)

                # Insere a disputa de 3º lugar logo antes da Grande Final
                if confrontos_3lugar:
                    matamata_fases.append({ "fase": "Disputa de 3º Lugar", "jogos": confrontos_3lugar })
                if confrontos_principais:
                    matamata_fases.append({ "fase": nome_fase, "jogos": confrontos_principais })
                
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