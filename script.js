const ATRASO_SEGUNDOS_PADRAO = 3;
const ATRASO_SEGUNDOS_BASQUETE = 15;
const ATRASO_SEGUNDOS_TROCA = 0.5;

let filaSnapshots = [];
let idPartidaAtiva = null;

let placarSalvoCasa = localStorage.getItem('placarCasa') !== null ? parseInt(localStorage.getItem('placarCasa')) : null;
let placarSalvoFora = localStorage.getItem('placarFora') !== null ? parseInt(localStorage.getItem('placarFora')) : null;
let ultimoAlertaTime = 0;
let tempoAnteriorBruto = null;
let animando = false;
let minutosLocais = 0;
let segundosLocais = 0;
let relogioRodando = false;
let painelAberto = false;
let dadosPartidaAtual = null;
let vermelhosSalvosCasa = null;
let vermelhosSalvosFora = null;

let alerta2MinQ2 = false;
let alerta2MinQ4 = false;
let indiceTesteO = 0;
let historicoOutrosJogos = {};

let lastPlacarState = "";
let lastPainelState = "";
let lastTabelaState = "";

let tabelaAberta = false;
const btnTabela = document.getElementById('btn-tabela');
const btnEscalacao = document.getElementById('btn-escalacao');
const painelTabela = document.getElementById('painel-tabela');

window.subAbaTabela = 'grupos';
window.indiceGrupoSelecionado = 0;
window.usuarioEscolheuGrupo = false;
window.idJogoTabelaIniciado = "";

btnTabela.addEventListener('click', (e) => {
    e.stopPropagation();
    tabelaAberta = !tabelaAberta;
    if (tabelaAberta) {
        painelTabela.classList.add('aberto');
        btnTabela.classList.add('ativa');
        painelAberto = false;
        document.getElementById('painel-escalacoes').classList.remove('aberto');
        if (btnEscalacao) btnEscalacao.classList.remove('ativa');
    } else {
        painelTabela.classList.remove('aberto');
        btnTabela.classList.remove('ativa');
    }
});

if (btnEscalacao) {
    btnEscalacao.addEventListener('click', (e) => {
        e.stopPropagation();
        painelAberto = !painelAberto;
        const painelEsc = document.getElementById('painel-escalacoes');
        if (painelAberto) {
            painelEsc.classList.add('aberto');
            btnEscalacao.classList.add('ativa');
            tabelaAberta = false;
            painelTabela.classList.remove('aberto');
            btnTabela.classList.remove('ativa');
        } else {
            painelEsc.classList.remove('aberto');
            btnEscalacao.classList.remove('ativa');
        }
    });
}


// CLIQUE NO CARD (Se a tabela estiver aberta, apenas fecha sem abrir a escalação)
document.getElementById('card-principal').addEventListener('click', (e) => {
    if (e.target.closest('.aba-btn') ||
        e.target.closest('#btn-tabela') ||
        e.target.closest('#btn-escalacao') ||
        e.target.closest('#painel-tabela') ||
        e.target.closest('#painel-escalacoes')) return;

    if (tabelaAberta) {
        tabelaAberta = false;
        painelTabela.classList.remove('aberto');
        btnTabela.classList.remove('ativa');
        return;
    }

    const painel = document.getElementById('painel-escalacoes');
    if (painel.style.display === 'none') return;

    painelAberto = !painelAberto;
    if (painelAberto) {
        painel.classList.add('aberto');
        if (btnEscalacao) btnEscalacao.classList.add('ativa');
    } else {
        painel.classList.remove('aberto');
        if (btnEscalacao) btnEscalacao.classList.remove('ativa');
        painel.classList.remove('modo-reservas');
        document.getElementById('btn-titulares').classList.add('ativa');
        document.getElementById('btn-reservas').classList.remove('ativa');
    }
});

document.getElementById('btn-titulares').addEventListener('click', (e) => {
    e.stopPropagation();
    document.getElementById('painel-escalacoes').classList.remove('modo-reservas');
    document.getElementById('btn-titulares').classList.add('ativa');
    document.getElementById('btn-reservas').classList.remove('ativa');
});

document.getElementById('btn-reservas').addEventListener('click', (e) => {
    e.stopPropagation();
    document.getElementById('painel-escalacoes').classList.add('modo-reservas');
    document.getElementById('btn-reservas').classList.add('ativa');
    document.getElementById('btn-titulares').classList.remove('ativa');
});

window.trocarSubAba = function (tipo) {
    window.subAbaTabela = tipo;
    lastTabelaState = "";
    if (dadosPartidaAtual) aplicarNaTela([dadosPartidaAtual]);
};

window.trocarGrupo = function (idx) {
    window.indiceGrupoSelecionado = idx;
    window.usuarioEscolheuGrupo = true;
    lastTabelaState = "";
    if (dadosPartidaAtual) aplicarNaTela([dadosPartidaAtual]);
};

document.addEventListener('wheel', (e) => {
    const bar = document.querySelector('.seletor-grupos-bar');
    if (bar && bar.contains(e.target)) {
        e.preventDefault();
        bar.scrollLeft += e.deltaY;
    }
}, { passive: false });

window.addEventListener('keydown', (e) => {
    const tecla = e.key.toLowerCase();
    const modalidadeAtual = dadosPartidaAtual ? dadosPartidaAtual.esporte : 'futebol';

    if (tecla === '1' || tecla === 't') {
        if (modalidadeAtual !== 'nfl') return;
        dispararEvento("TOUCHDOWN!", "tema-td");
    }
    else if (tecla === '3' || tecla === 'k') {
        if (modalidadeAtual !== 'nfl') return;
        dispararEvento("FIELD GOAL!", "tema-fg");
    }
    else if (tecla === 'w') {
        if (modalidadeAtual !== 'nfl') return;
        dispararEvento("2-MINUTE WARNING!", "tema-2min");
    }
    else if (tecla === 'f') {
        if (modalidadeAtual === 'futebol') return;
        dispararEvento("FIM DE QUARTO!", modalidadeAtual === 'basquete' ? "tema-quarto-basq" : "tema-quarto-nfl");
    }
    else if (tecla === 'g') {
        if (modalidadeAtual !== 'futebol') return;
        const logo = dadosPartidaAtual ? (dadosPartidaAtual.logoCasa || "") : "";
        dispararEvento("GOOOOOOL!", "tema-gol", Boolean(logo), logo);
    }
    else if (tecla === 'o') {
        if (modalidadeAtual !== 'futebol' && modalidadeAtual !== 'basquete') return;
        if (!dadosPartidaAtual || !dadosPartidaAtual.outros_jogos || dadosPartidaAtual.outros_jogos.length === 0) return;

        const lista = dadosPartidaAtual.outros_jogos;
        if (indiceTesteO >= lista.length) indiceTesteO = 0;

        const j = lista[indiceTesteO];
        const p1 = parseInt(j.placar1) || 0;
        const p2 = parseInt(j.placar2) || 0;

        let timeDestaque = j.time1, logoDestaque = j.logo1;
        if (p2 > p1) { timeDestaque = j.time2; logoDestaque = j.logo2; }

        const badge = (modalidadeAtual === 'basquete') ? "🏀 RODADA" : "⚽ RODADA";

        dispararAlertaGolExterno({
            badgeTexto: badge,
            timeGol: timeDestaque,
            logoGol: logoDestaque,
            time1: j.time1,
            placar1: p1,
            time2: j.time2,
            placar2: p2,
            tempo: j.status || 'AO VIVO',
            esporte: modalidadeAtual
        });

        indiceTesteO++;
    }
    else if (tecla === 'v') {
        if (modalidadeAtual !== 'futebol') return;
        const logo = dadosPartidaAtual ? ("") : "";
        dispararEvento("CARTÃO VERMELHO!", "tema-vermelho", Boolean(logo), logo);
    }
});

function dispararEvento(texto, classeTema, usaImg = false, logoSrc = "") {
    animando = true;
    const tela = document.getElementById('camada-animacao');
    const img = document.getElementById('img-anim');
    document.getElementById('texto-anim').innerText = texto;

    if (texto.includes("GOOOOOOL")) {
        let audio = new Audio('alertaGOL.mp3');
        audio.volume = 0.5;
        audio.play().catch(e => console.log("Áudio bloqueado: ", e));
    } else if (texto.includes("TOUCHDOWN")) {
        let audio = new Audio('alertaTOUCHDOWN.mp3');
        audio.volume = 0.5;
        audio.play().catch(e => console.log("Áudio bloqueado: ", e));
    }

    if (usaImg && logoSrc && logoSrc.trim() !== "") {
        img.src = logoSrc; img.style.display = 'block';
    } else {
        img.style.display = 'none';
    }

    tela.className = `tela-anim ${classeTema} mostrar`;
    setTimeout(() => { tela.className = 'tela-anim'; animando = false; }, 6000);
}

let timerAlertaExterno = null;
function dispararAlertaGolExterno(dados) {
    const container = document.getElementById('container-alerta-externo');
    if (!container) return;
    if (timerAlertaExterno) clearTimeout(timerAlertaExterno);

    const badgeTexto = dados.badgeTexto || "⚽ GOL!";
    const classeEsporte = (dados.esporte === 'basquete') ? 'basquete' : '';

    container.innerHTML = `
                <div class="notificacao-gol-externo ${classeEsporte}">
                    <span class="badge-gol-pulsar">${badgeTexto}</span>
                    <img src="${dados.logoGol}" class="logo-alerta-gol" onerror="this.style.display='none'">
                    <span class="time-gol-destaque" title="${dados.timeGol}">${dados.timeGol}</span>
                    <div class="placar-alerta-caixa">
                        <span class="nome-time-min" title="${dados.time1}">${dados.time1}</span>
                        <span>${dados.placar1} - ${dados.placar2}</span>
                        <span class="nome-time-min" title="${dados.time2}">${dados.time2}</span>
                    </div>
                    <span class="tempo-alerta">(${dados.tempo})</span>
                </div>`;

    timerAlertaExterno = setTimeout(() => { container.innerHTML = ''; }, 7500);
}

function verificarGolsOutrosJogos(listaOutros, timePrincipalCasa, timePrincipalFora) {
    if (!listaOutros || !Array.isArray(listaOutros)) return;
    const tCasa = (timePrincipalCasa || "").toLowerCase(), tFora = (timePrincipalFora || "").toLowerCase();

    listaOutros.forEach(jogo => {
        const id = jogo.id, p1 = parseInt(jogo.placar1), p2 = parseInt(jogo.placar2);
        if (isNaN(p1) || isNaN(p2)) return;

        const j1 = jogo.time1.toLowerCase(), j2 = jogo.time2.toLowerCase();
        if (tCasa.includes(j1) || j1.includes(tCasa) || tFora.includes(j2) || j2.includes(tFora)) return;

        if (!historicoOutrosJogos[id]) {
            historicoOutrosJogos[id] = { p1: p1, p2: p2 };
        } else {
            const ant = historicoOutrosJogos[id];
            if (p1 > ant.p1) {
                dispararAlertaGolExterno({ timeGol: jogo.time1, logoGol: jogo.logo1, time1: jogo.time1, placar1: p1, time2: jogo.time2, placar2: p2, tempo: jogo.status || 'AO VIVO' });
            } else if (p2 > ant.p2) {
                dispararAlertaGolExterno({ timeGol: jogo.time2, logoGol: jogo.logo2, time1: jogo.time1, placar1: p1, time2: jogo.time2, placar2: p2, tempo: jogo.status || 'AO VIVO' });
            }
            historicoOutrosJogos[id].p1 = p1; historicoOutrosJogos[id].p2 = p2;
        }
    });
}

function objClsRtg(val) {
    let n = parseFloat(val);
    if (isNaN(n)) return 'rating-neutra';
    if (n >= 10) return 'rating-10';
    if (n >= 7) return 'rating-alta';
    if (n >= 6) return 'rating-media';
    return 'rating-baixa';
}

function htmlFut(j, isReserva = false) {
    let cC = objClsRtg(j.rating);
    const fallbackFoto = "https://pbs.twimg.com/profile_images/1858822306186878976/qPsDCLmQ_400x400.jpg";
    let tf = `<img src="${j.foto || fallbackFoto}" class="jogador-foto" onerror="this.src='${fallbackFoto}'">`;
    let tr = `<span class="jogador-rating ${cC}">${j.rating}</span>`;
    let tn = (j.numero && j.numero !== '-') ? `<span class="jogador-numero">${j.numero}</span>` : `<span class="jogador-numero"></span>`;
    let flagHtml = j.nacionalidade ? `<img src="https://flagcdn.com/w40/${j.nacionalidade}.png" class="bandeira-jogador" onerror="this.style.display='none'">` : '';

    let clSubs = '';
    let subInfo = '';
    const fezGol = (j.gols_count > 0 || j.gol);

    let bg = '';
    if (j.capitao) bg += `<span class="badge-capitao">C</span>`;
    if (j.amarelo) bg += `<span class="badge-cartao amarelo"></span>`;
    if (j.vermelho) bg += `<span class="badge-cartao vermelho"></span>`;

    // ==============================================================
    // 1. CASO O JOGADOR TENHA SIDO EXPULSO (PRESERVA GOLS E ASSISTS)
    // ==============================================================
    if (j.vermelho) {
        clSubs = 'expulso';

        let tagGol = '';
        let tagAssist = '';

        subInfo = `<span class="info-sub">${tagGol}${tagAssist}<span style="color: #f87171; font-weight: 800;">🟥 Expulso</span></span>`;

        // Mantém também o badge visual de gol ao lado do cartão vermelho
        if (j.gols_count > 1) bg += `<span class="badge-evento">⚽x${j.gols_count}</span>`;
        else if (j.gol) bg += `<span class="badge-evento">⚽</span>`;

        // ==============================================================
        // 2. TITULARES QUE NÃO FORAM EXPULSOS
        // ==============================================================
    } else if (!isReserva) {
        if (j.saiu) {
            clSubs = j.lesao ? 'saiu-lesao' : 'saiu-normal';
            let tagGol = '';
            if (fezGol) {
                const txtGols = (j.gols_count > 1) ? `⚽ ${j.gols_count} Gols` : `⚽ 1 Gol`;
                tagGol = `<span style="color: #60a5fa; font-weight: 800;">${txtGols}</span> • `;
            }

            if (j.lesao) {
                subInfo = `<span class="info-sub in"><span style="color:#f87171;">🚑 Lesão</span> • ${tagGol}▲ Entrou: ${j.sub_nome}</span>`;
            } else {
                subInfo = `<span class="info-sub in">${tagGol}▲ Entrou: ${j.sub_nome || 'Substituído'}</span>`;
            }
        } else {
            if (j.gols_count > 1) bg += `<span class="badge-evento">⚽x${j.gols_count}</span>`;
            else if (j.gol) bg += `<span class="badge-evento">⚽</span>`;
        }

        // ==============================================================
        // 3. RESERVAS
        // ==============================================================
    } else {
        if (j.gols_count > 1) bg += `<span class="badge-evento">⚽x${j.gols_count}</span>`;
        else if (j.gol) bg += `<span class="badge-evento">⚽</span>`;

        if (j.entrou) {
            subInfo = `<span class="info-sub out">▼ Saiu: ${j.sub_nome || 'Em campo'}</span>`;
        }
    }

    if (j.gols_contra_count > 1) bg += `<span class="badge-gc">⚽ GC x${j.gols_contra_count}</span>`;
    else if (j.gol_contra) bg += `<span class="badge-gc">⚽ GC</span>`;

    if (j.assists_count > 1) bg += `<span class="badge-evento">👟x${j.assists_count}</span>`;
    else if (j.assist) bg += `<span class="badge-evento">👟</span>`;

    let extraClass = isReserva ? 'reserva-item' : '';

    return `<div class="jogador-item ${clSubs} ${extraClass}">
                <div class="jogador-info">
                    ${tf}${tn}
                    <div class="nome-container">
                        <div style="display: flex; align-items: center;">
                            ${flagHtml}
                            <span class="jogador-nome">${j.nome}</span>
                        </div>
                        ${subInfo}
                    </div>
                    <div class="eventos-badge">${bg}</div>
                </div>
                <div class="rating-slot">${tr}</div>
            </div>`;
}

function htmlBasq(j) {
    let cC = objClsRtg(j.rating);
    const fallbackFoto = "https://pbs.twimg.com/profile_images/1858822306186878976/qPsDCLmQ_400x400.jpg";
    let tf = `<img src="${j.foto || fallbackFoto}" class="jogador-foto" onerror="this.src='${fallbackFoto}'">`;
    let tr = `<span class="jogador-rating ${cC}">${j.rating}</span>`;
    let flagHtml = j.nacionalidade ? `<img src="https://flagcdn.com/w40/${j.nacionalidade}.png" class="bandeira-jogador" onerror="this.style.display='none'">` : '';

    return `<div class="jogador-item">
                <div class="jogador-info">
                    ${tf}
                    <div style="display: flex; align-items: center;">
                        ${flagHtml}
                        <span class="jogador-nome">${j.nome}</span>
                    </div>
                </div>
                <div class="stats-wrapper">
                    <div class="estatisticas-jogador">
                        <span class="stat-box pts">${j.pts}</span>
                        <span class="stat-box">${j.reb}</span>
                        <span class="stat-box">${j.ast}</span>
                    </div>
                    <div class="rating-slot">${tr}</div>
                </div>
            </div>`;
}

function renderNflLider(ldr) {
    const cat = ldr.categoria || "";
    const away = ldr.away, home = ldr.home;

    let pAwayHtml = `<div class="nfl-player away"><div class="nfl-player-photo empty"></div><div class="nfl-player-info"><div class="nfl-player-name-line"><span class="nfl-pname" style="opacity:0.4;">Nenhum</span></div></div></div>`;
    let valAway = "--";
    if (away) {
        let fAway = away.foto ? `<img src="${away.foto}" class="nfl-player-photo" onerror="this.style.display='none'">` : `<div class="nfl-player-photo empty"></div>`;
        pAwayHtml = `<div class="nfl-player away">${fAway}<div class="nfl-player-info"><div class="nfl-player-name-line"><span class="nfl-pname">${away.nome}</span>${away.posicao ? `<span class="nfl-player-pos">${away.posicao}</span>` : ''}</div>${away.detalhe ? `<span class="nfl-player-stat-detail">${away.detalhe}</span>` : ''}</div></div>`;
        valAway = away.stat || "-";
    }

    let pHomeHtml = `<div class="nfl-player home"><div class="nfl-player-info"><div class="nfl-player-name-line">${home.posicao ? `<span class="nfl-player-pos">${home.posicao}</span>` : ''}<span class="nfl-pname">${home.nome}</span></div>${home.detalhe ? `<span class="nfl-player-stat-detail">${home.detalhe}</span>` : ''}</div><div class="nfl-player-photo empty"></div></div>`;
    let valHome = "--";
    if (home) {
        let fHome = home.foto ? `<img src="${home.foto}" class="nfl-player-photo" onerror="this.style.display='none'">` : `<div class="nfl-player-photo empty"></div>`;
        pHomeHtml = `<div class="nfl-player home"><div class="nfl-player-info"><div class="nfl-player-name-line">${home.posicao ? `<span class="nfl-player-pos">${home.posicao}</span>` : ''}<span class="nfl-pname">${home.nome}</span></div>${home.detalhe ? `<span class="nfl-player-stat-detail">${home.detalhe}</span>` : ''}</div>${fHome}</div>`;
        valHome = home.stat || "-";
    }

    return `<div class="nfl-row">${pAwayHtml}<div class="nfl-stat-center"><span class="nfl-stat-val away">${valAway}</span><span class="nfl-stat-label">${cat}</span><span class="nfl-stat-val home">${valHome}</span></div>${pHomeHtml}</div>`;
}

async function buscarDadosServidor() {
    try {
        const res = await fetch('dados.json?t=' + Date.now(), { cache: 'no-store' });
        const d = await res.json();
        if (d && d.length > 0) {
            const jg = d[0];
            const idNovoJogo = `${jg.esporte}_${jg.timeCasa}_${jg.timeFora}`;

            if (idPartidaAtiva !== null && idPartidaAtiva !== idNovoJogo) {
                filaSnapshots = [];
                placarSalvoCasa = null;
                placarSalvoFora = null;
                localStorage.removeItem('placarCasa');
                localStorage.removeItem('placarFora');
                ultimoAlertaTime = 0;
                tempoAnteriorBruto = null;
                relogioRodando = false;
                alerta2MinQ2 = false;
                alerta2MinQ4 = false;
                lastTabelaState = "";
                window.idJogoTabelaIniciado = "";
                window.usuarioEscolheuGrupo = false;
                vermelhosSalvosCasa = null;
                vermelhosSalvosFora = null;

                const containerAlerta = document.getElementById('container-alerta-externo');
                if (containerAlerta) containerAlerta.innerHTML = '';

                filaSnapshots.push({
                    momento: Date.now(),
                    dados: d,
                    isTrocaJogo: true
                });
                idPartidaAtiva = idNovoJogo;
            } else {
                const isPrimeiraVez = (idPartidaAtiva === null);
                if (isPrimeiraVez) idPartidaAtiva = idNovoJogo;

                filaSnapshots.push({
                    momento: Date.now(),
                    dados: d,
                    isTrocaJogo: isPrimeiraVez
                });
            }
        }
    } catch (e) { }
}

function processarFilaAntiSpoiler() {
    if (filaSnapshots.length === 0) return;

    const agora = Date.now();
    let indiceEscolhido = -1;

    for (let i = filaSnapshots.length - 1; i >= 0; i--) {
        const snapshot = filaSnapshots[i];
        const esp = (snapshot.dados && snapshot.dados[0]) ? snapshot.dados[0].esporte : 'futebol';

        let delaySegundos;
        if (esp === 'f1') {
            delaySegundos = 0;
        } else if (snapshot.isTrocaJogo) {
            delaySegundos = ATRASO_SEGUNDOS_TROCA;
        } else {
            delaySegundos = (esp === 'basquete') ? ATRASO_SEGUNDOS_BASQUETE : ATRASO_SEGUNDOS_PADRAO;
        }
        const limiteAtraso = agora - (delaySegundos * 1000);

        if (snapshot.momento <= limiteAtraso) {
            indiceEscolhido = i;
            break;
        }
    }

    if (indiceEscolhido !== -1) {
        aplicarNaTela(filaSnapshots[indiceEscolhido].dados);
        filaSnapshots = filaSnapshots.slice(indiceEscolhido);
    }
}

function aplicarNaTela(d) {
    try {
        if (!d || d.length === 0) return;

        const jg = d[0];
        dadosPartidaAtual = jg;
        const cnt = document.getElementById('card-principal');
        const painelConteudo = document.getElementById('container-conteudo');

        cnt.className = "container " + jg.esporte;
        if (jg.torneio) document.getElementById('txt-torneio').innerText = jg.torneio;
        if (jg.estadio) document.getElementById('txt-estadio').innerText = jg.estadio;

        // ==========================================
        // ROTA DA F1
        // ==========================================
        if (jg.esporte === "f1") {
            cnt.removeAttribute('title');

            let abaAtiva = jg.abaAtiva || "Corrida";
            let subTreino = jg.subTreino || "Treino 1";
            let currentPlacarState = JSON.stringify({ sessao: abaAtiva, sub: subTreino, dados: jg.classificacaoF1 });

            if (currentPlacarState !== lastPlacarState) {
                const isTreinoAtivo = (abaAtiva === 'Treino' || abaAtiva.startsWith('Treino '));

                const abasHtml = `
                            <div class="f1-menu-bar">
                                <div class="f1-botoes-grupo">
                                    <button class="aba-f1 aba-btn ${isTreinoAtivo ? 'ativa-f1' : ''}" data-sessao="Treino 1">TREINO</button>
                                    <button class="aba-f1 aba-btn ${abaAtiva === 'Sprint' ? 'ativa-f1' : ''}" data-sessao="Sprint">SPRINT</button>
                                    <button class="aba-f1 aba-btn ${abaAtiva === 'Quali' ? 'ativa-f1' : ''}" data-sessao="Quali">QUALI</button>
                                    <button class="aba-f1 aba-btn ${abaAtiva === 'Corrida' ? 'ativa-f1' : ''}" data-sessao="Corrida">CORRIDA</button>
                                </div>
                                <span class="f1-divisor-pipe">|</span>
                                <div class="f1-botoes-grupo">
                                    <button class="aba-f1 aba-btn ${abaAtiva === 'Pilotos' ? 'ativa-f1' : ''}" data-sessao="Pilotos">PILOTOS</button>
                                    <button class="aba-f1 aba-btn ${abaAtiva === 'Equipes' ? 'ativa-f1' : ''}" data-sessao="Equipes">CONSTRUTORES</button>
                                </div>
                            </div>
                        `;

                let subTreinoHtml = '';
                if (isTreinoAtivo) {
                    subTreinoHtml = `
                                <div style="display: flex; justify-content: center; gap: 6px; margin-bottom: 8px;">
                                    <button class="aba-f1 aba-btn ${subTreino === 'Treino 1' ? 'ativa-f1' : ''}" data-sessao="Treino 1" style="font-size:0.65rem; padding: 2px 10px;">TREINO 1</button>
                                    <button class="aba-f1 aba-btn ${subTreino === 'Treino 2' ? 'ativa-f1' : ''}" data-sessao="Treino 2" style="font-size:0.65rem; padding: 2px 10px;">TREINO 2</button>
                                    <button class="aba-f1 aba-btn ${subTreino === 'Treino 3' ? 'ativa-f1' : ''}" data-sessao="Treino 3" style="font-size:0.65rem; padding: 2px 10px;">TREINO 3</button>
                                </div>
                            `;
                }

                let cabecalhoHtml = '';
                if (abaAtiva === 'Equipes') {
                    cabecalhoHtml = `
                                <div class="tabela-f1-cabecalho">
                                    <div class="col-f1-piloto">POS / ESCUDERIA</div>
                                    <div class="col-f1-tempos" style="width: 80px; justify-content: flex-end;">
                                        <span style="width: 60px; text-align: right; color:#ef4444;">PONTOS</span>
                                    </div>
                                </div>`;
                } else if (abaAtiva === 'Pilotos') {
                    cabecalhoHtml = `
                                <div class="tabela-f1-cabecalho">
                                    <div class="col-f1-piloto">POS / PILOTO</div>
                                    <div class="col-f1-tempos" style="width: 240px; justify-content: space-between;">
                                        <span style="width: 160px; text-align: left;">EQUIPE</span>
                                        <span style="width: 60px; text-align: right; color:#ef4444;">PONTOS</span>
                                    </div>
                                </div>`;
                } else if (abaAtiva === 'Quali') {
                    cabecalhoHtml = `
                                <div class="tabela-f1-cabecalho">
                                    <div class="col-f1-piloto">POS / PILOTO</div>
                                    <div class="col-f1-tempos" style="width: 290px;">
                                        <span style="width: 74px; text-align: center;">Q1</span>
                                        <span style="width: 74px; text-align: center;">Q2</span>
                                        <span style="width: 74px; text-align: center; color:#ef4444;">Q3</span>
                                        <span style="width: 44px; text-align: center;">VOLT</span>
                                    </div>
                                </div>`;
                } else if (abaAtiva === 'Corrida' || abaAtiva === 'Sprint') {
                    cabecalhoHtml = `
                                <div class="tabela-f1-cabecalho">
                                    <div class="col-f1-piloto">POS / PILOTO</div>
                                    <div class="col-f1-tempos" style="width: 230px;">
                                        <span style="width: 120px; text-align: center;">TEMPO / GAP</span>
                                        <span style="width: 45px; text-align: center;">VOLT</span>
                                        <span style="width: 45px; text-align: center; color:#ef4444;">PTS</span>
                                    </div>
                                </div>`;
                } else {
                    cabecalhoHtml = `
                                <div class="tabela-f1-cabecalho">
                                    <div class="col-f1-piloto">POS / PILOTO</div>
                                    <div class="col-f1-tempos" style="width: 180px;">
                                        <span style="width: 120px; text-align: center;">TEMPO / GAP</span>
                                        <span style="width: 45px; text-align: center;">VOLT</span>
                                    </div>
                                </div>`;
                }

                let linhas = (jg.classificacaoF1 || []).map(p => {
                    if (p.piloto === "Sem resultados") {
                        return `<div class="linha-f1" style="justify-content:center; color:#94a3b8; font-weight:bold; padding: 20px;">
                                    Sem resultados
                                </div>`;
                    }

                    let logoBadgeHtml = p.logoEquipe ? `
                                <span class="badge-logo-equipe" style="background-color: ${p.corEquipe || 'rgba(255,255,255,0.08)'};">
                                    <img src="${p.logoEquipe}" class="logo-equipe-img" onerror="this.style.display='none'">
                                </span>` : '';

                    if (p.isEquipes) {
                        return `<div class="linha-f1">
                                    <div class="col-f1-piloto">
                                        <span class="badge-pos-f1">${p.pos}</span>
                                        ${logoBadgeHtml}
                                        <span style="font-weight: 800; font-size: 0.85rem; color: #fff;">${p.equipe}</span>
                                    </div>
                                    <div class="col-f1-tempos" style="width: 80px; justify-content: flex-end;">
                                        <span style="font-size: 0.95rem; font-weight: 900; color: #ef4444; width: 60px; text-align: right;">${p.pts}</span>
                                    </div>
                                </div>`;
                    }

                    let fotoContainerHtml = p.foto ? `
                                <div class="foto-container-f1">
                                    <img src="${p.foto}" class="foto-piloto-f1" onerror="this.style.display='none'">
                                </div>` : '';

                    let flagHtml = p.nacionalidade ? `<img src="https://flagcdn.com/w40/${p.nacionalidade}.png" style="width:16px; height:11px; object-fit:cover; border-radius:2px; margin-right:6px;" onerror="this.style.display='none'">` : '';

                    let temposLinhaHtml = '';
                    if (abaAtiva === 'Pilotos') {
                        temposLinhaHtml = `
                                    <div class="col-f1-tempos" style="width: 240px; justify-content: space-between;">
                                        <div style="display:flex; align-items:center; width:160px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
                                            ${logoBadgeHtml}
                                            <span style="color:#94a3b8; font-weight:600; font-size:0.75rem;">${p.equipe}</span>
                                        </div>
                                        <span style="width: 60px; text-align: right; font-size: 0.95rem; font-weight: 900; color: #ef4444;">${p.pts}</span>
                                    </div>`;
                    } else if (abaAtiva === 'Quali') {
                        temposLinhaHtml = `
                                    <div class="col-f1-tempos" style="width: 290px;">
                                        <span style="width: 74px; text-align: center;">${p.q1 || '-'}</span>
                                        <span style="width: 74px; text-align: center;">${p.q2 || '-'}</span>
                                        <span style="width: 74px; text-align: center; color: ${p.q3 && p.q3 !== '-' ? '#4ade80' : 'inherit'};">${p.q3 || '-'}</span>
                                        <span style="width: 44px; text-align: center; color:#94a3b8;">${p.laps || '-'}</span>
                                    </div>`;
                    } else if (abaAtiva === 'Corrida' || abaAtiva === 'Sprint') {
                        let timeColor = p.isOut ? '#ef4444' : 'inherit';
                        temposLinhaHtml = `
                                    <div class="col-f1-tempos" style="width: 230px;">
                                        <span style="width: 120px; text-align: center; font-weight: ${p.isOut ? '900' : '700'}; color: ${timeColor};">${p.timeGap || '-'}</span>
                                        <span style="width: 45px; text-align: center; color:#94a3b8;">${p.laps || '-'}</span>
                                        <span style="width: 45px; text-align: center; font-weight:900; color:#ef4444;">${p.pts || '0'}</span>
                                    </div>`;
                    } else {
                        temposLinhaHtml = `
                                    <div class="col-f1-tempos" style="width: 180px;">
                                        <span style="width: 120px; text-align: center;">${p.timeGap || '-'}</span>
                                        <span style="width: 45px; text-align: center; color:#94a3b8;">${p.laps || '-'}</span>
                                    </div>`;
                    }

                    let classeOut = p.isOut ? 'piloto-out' : '';
                    let equipaNomeHtml = (abaAtiva !== 'Pilotos' && p.equipe) ? ` <small style="color:#94a3b8; font-weight:600;">(${p.equipe})</small>` : '';

                    return `<div class="linha-f1 ${classeOut}">
                                <div class="col-f1-piloto">
                                    <span class="badge-pos-f1">${p.pos}</span>
                                    ${logoBadgeHtml}
                                    ${fotoContainerHtml}
                                    ${flagHtml}
                                    <span style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis;"><strong>${p.piloto}</strong>${equipaNomeHtml}</span>
                                </div>
                                ${temposLinhaHtml}
                            </div>`;
                }).join('');

                document.getElementById('placar-dinamico').innerHTML = abasHtml + subTreinoHtml + cabecalhoHtml + `<div class="scroll-f1">${linhas}</div>`;
                document.getElementById('painel-escalacoes').style.display = 'none';

                document.querySelectorAll('.aba-f1').forEach(btn => {
                    btn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        let sessaoEscolhida = e.target.getAttribute('data-sessao');
                        document.querySelectorAll('.aba-f1').forEach(b => b.classList.remove('ativa-f1'));
                        e.target.classList.add('ativa-f1');

                        if (sessaoEscolhida.startsWith('Treino')) {
                            let btnTreinoPrincipal = document.querySelector('.aba-f1[data-sessao="Treino 1"]:not([style])');
                            if (btnTreinoPrincipal) btnTreinoPrincipal.classList.add('ativa-f1');
                        }

                        fetch('/trocar_sessao_f1', { method: 'POST', body: sessaoEscolhida }).catch(() => { });
                        setTimeout(buscarDadosServidor, 350);
                        setTimeout(buscarDadosServidor, 700);
                    });
                });

                lastPlacarState = currentPlacarState;
            }

            document.getElementById('txt-estadio').innerText = jg.tempo;
            return;
        } else {
            document.getElementById('painel-escalacoes').style.display = 'block';
        }

        if (jg.outros_jogos && jg.esporte === "futebol") {
            verificarGolsOutrosJogos(jg.outros_jogos, jg.timeCasa, jg.timeFora);
        }

        // 1. CHECAGEM DE GOLS / PONTOS (SEU IF ORIGINAL INTACTO)
        let aC = parseInt(jg.placarCasa), aF = parseInt(jg.placarFora);
        if (!isNaN(aC) && !isNaN(aF)) {
            if (placarSalvoCasa === null) { placarSalvoCasa = aC; localStorage.setItem('placarCasa', aC); }
            if (placarSalvoFora === null) { placarSalvoFora = aF; localStorage.setItem('placarFora', aF); }

            let dC = aC - placarSalvoCasa, dF = aF - placarSalvoFora, agora = Date.now();
            if ((dC > 0 || dF > 0) && (agora - ultimoAlertaTime > 6000)) {
                if (jg.esporte === "futebol") {
                    if (dC > 0) dispararEvento(`GOOOOOOL ${jg.timeCasa}!`, "tema-gol", true, jg.logoCasa);
                    else dispararEvento(`GOOOOOOL ${jg.timeFora}!`, "tema-gol", true, jg.logoFora);
                } else if (jg.esporte === "nfl") {
                    if (dC >= 6 || dF >= 6) dispararEvento("TOUCHDOWN!", "tema-td");
                    else if (dC === 3 || dF === 3) dispararEvento("FIELD GOAL!", "tema-fg");
                }
                ultimoAlertaTime = agora;
            }
            placarSalvoCasa = aC; placarSalvoFora = aF;
            localStorage.setItem('placarCasa', aC); localStorage.setItem('placarFora', aF);
        }

        // 2. CHECAGEM DE CARTÃO VERMELHO (INDEPENDENTE DO PLACAR)
        if (jg.esporte === "futebol") {
            let totalVermelhosCasa = (jg.escalacaoCasa || []).filter(j => j.vermelho).length;
            let totalVermelhosFora = (jg.escalacaoFora || []).filter(j => j.vermelho).length;

            if (vermelhosSalvosCasa === null) vermelhosSalvosCasa = totalVermelhosCasa;
            if (vermelhosSalvosFora === null) vermelhosSalvosFora = totalVermelhosFora;

            let novoVermelhoCasa = totalVermelhosCasa > vermelhosSalvosCasa;
            let novoVermelhoFora = totalVermelhosFora > vermelhosSalvosFora;
            let agoraExp = Date.now();

            if ((novoVermelhoCasa || novoVermelhoFora) && (agoraExp - ultimoAlertaTime > 6000)) {
                if (novoVermelhoCasa) {
                    dispararEvento(`CARTÃO VERMELHO ${jg.timeCasa}!`, "tema-vermelho", true, jg.logoCasa);
                } else {
                    dispararEvento(`CARTÃO VERMELHO ${jg.timeFora}!`, "tema-vermelho", true, jg.logoFora);
                }
                ultimoAlertaTime = agoraExp;
            }

            vermelhosSalvosCasa = totalVermelhosCasa;
            vermelhosSalvosFora = totalVermelhosFora;
        }

        let tBruto = (jg.tempo || "").trim(), tLower = tBruto.toLowerCase();
        const tParadas = ["finalizado", "encerrado", "fim", "ft", "terminado", "intervalo", "ht", "half-time", "adiado", "pausa"];
        let jogoParado = tParadas.some(w => tLower.includes(w));

        if ((jg.esporte === "basquete" || jg.esporte === "nfl") && tempoAnteriorBruto !== null && tempoAnteriorBruto !== tBruto) {
            let tOld = tempoAnteriorBruto.toLowerCase();
            let isBrkNow = tParadas.some(w => tLower.includes(w)), wasBrk = tParadas.some(w => tOld.includes(w));
            if (isBrkNow && !wasBrk) {
                let txt = "FIM DE QUARTO!";
                if (tLower.includes("intervalo") || tLower.includes("ht")) txt = "INTERVALO!";
                if (tLower.includes("finalizado") || tLower.includes("fim")) txt = "FIM DE JOGO!";
                dispararEvento(txt, jg.esporte === "basquete" ? "tema-quarto-basq" : "tema-quarto-nfl");
            }
        }
        tempoAnteriorBruto = tBruto;

        if (jg.esporte === "nfl") {
            let isQ1 = tLower.includes("1º") || tLower.includes("1q") || tLower.includes("1°");
            let isQ2 = tLower.includes("2º") || tLower.includes("2q") || tLower.includes("2°");
            let isQ3 = tLower.includes("3º") || tLower.includes("3q") || tLower.includes("3°");
            let isQ4 = tLower.includes("4º") || tLower.includes("4q") || tLower.includes("4°");
            if (isQ1) alerta2MinQ2 = false;
            if (isQ3) alerta2MinQ4 = false;

            let isTwoMinExplicit = tLower.includes("two-minute") || tLower.includes("2-minute") || tLower.includes("2 minute") || tLower.includes("dois minutos");
            let matchTempo = tLower.match(/(\d+):(\d+)/), segundosRestantes = null;
            if (matchTempo) segundosRestantes = parseInt(matchTempo[1]) * 60 + parseInt(matchTempo[2]);

            if (isQ2 && !alerta2MinQ2 && (isTwoMinExplicit || (segundosRestantes !== null && segundosRestantes <= 120 && segundosRestantes >= 90))) {
                alerta2MinQ2 = true; dispararEvento("2-MINUTE WARNING!", "tema-2min");
            }
            if (isQ4 && !alerta2MinQ4 && (isTwoMinExplicit || (segundosRestantes !== null && segundosRestantes <= 120 && segundosRestantes >= 90))) {
                alerta2MinQ4 = true; dispararEvento("2-MINUTE WARNING!", "tema-2min");
            }
        }

        let ptTime = tBruto.split(':'), tExib = "";
        if (!jogoParado && ptTime.length === 2 && !isNaN(parseInt(ptTime[0])) && jg.esporte === "futebol") {
            let ms = parseInt(ptTime[0]), ss = parseInt(ptTime[1]);
            if (!relogioRodando || Math.abs((ms * 60 + ss) - (minutosLocais * 60 + segundosLocais)) > 15) {
                minutosLocais = ms; segundosLocais = ss; relogioRodando = true;
            }
            tExib = `${minutosLocais}:${segundosLocais.toString().padStart(2, '0')}`;
        } else { relogioRodando = false; tExib = tBruto.toUpperCase(); }

        if (!animando) {
            const inverterLados = (jg.esporte === 'nfl' || jg.esporte === 'basquete');

            let nomeEsquerda = inverterLados ? jg.timeFora : jg.timeCasa;
            let logoEsquerda = inverterLados ? jg.logoFora : jg.logoCasa;
            let placarEsquerda = inverterLados ? jg.placarFora : jg.placarCasa;
            let formacaoEsquerda = inverterLados ? jg.formacaoFora : jg.formacaoCasa;

            let nomeDireita = inverterLados ? jg.timeCasa : jg.timeFora;
            let logoDireita = inverterLados ? jg.logoCasa : jg.logoFora;
            let placarDireita = inverterLados ? jg.placarCasa : jg.placarFora;
            let formacaoDireita = inverterLados ? jg.formacaoCasa : jg.formacaoFora;

            let fEsq = formacaoEsquerda ? `<span class="time-formacao">${formacaoEsquerda}</span>` : '';
            let fDir = formacaoDireita ? `<span class="time-formacao">${formacaoDireita}</span>` : '';
            let separador = `<span style="font-size: 1.2rem; opacity: 0.5; margin: 0 4px;">-</span>`;

            let penaltisCentroHtml = '';
            let seqEsqHtml = '';
            let seqDirHtml = '';
            let clockDisplay = tExib;

            if (jg.temPenaltis) {
                let isHomeLeft = !inverterLados;
                const renderSeq = (seq) => seq.map(acerto => acerto ? `<span style="color: #4ade80; font-size: 1.2rem; filter: drop-shadow(0 0 2px rgba(74, 222, 128, 0.5)); line-height: 0.8;">●</span>` : `<span style="color: #ef4444; font-size: 1.2rem; font-weight: bold; filter: drop-shadow(0 0 2px rgba(239, 68, 68, 0.5)); line-height: 0.8;">x</span>`).join('');
                let htmlSeqEsq = isHomeLeft ? renderSeq(jg.seqPenCasa) : renderSeq(jg.seqPenFora);
                let htmlSeqDir = isHomeLeft ? renderSeq(jg.seqPenFora) : renderSeq(jg.seqPenCasa);
                let pEsq = isHomeLeft ? jg.scorePenCasa : jg.scorePenFora;
                let pDir = isHomeLeft ? jg.scorePenFora : jg.scorePenCasa;

                clockDisplay = '';
                penaltisCentroHtml = `<div style="color: #fb923c; font-size: 1.15rem; font-weight: 900; letter-spacing: 1px; margin-top: -2px;">PEN ${pEsq} - ${pDir}</div>`;
                seqEsqHtml = `<div style="display:flex; gap:4px; margin-top:4px; justify-content: flex-end;">${htmlSeqEsq}</div>`;
                seqDirHtml = `<div style="display:flex; gap:4px; margin-top:4px; justify-content: flex-start;">${htmlSeqDir}</div>`;
            }

            let currentPlacarState = JSON.stringify({ nomeEsquerda, fEsq, logoEsquerda, placarEsquerda, placarDireita, nomeDireita, fDir, logoDireita, tp: jg.temPenaltis, spc: jg.scorePenCasa, spf: jg.scorePenFora, sqc: jg.seqPenCasa, sqf: jg.seqPenFora, t: clockDisplay });

            if (currentPlacarState !== lastPlacarState) {
                document.getElementById('placar-dinamico').innerHTML = `
                            <div class="placar-wrapper">
                                <div class="time-box casa">
                                    <div class="textos-time casa">
                                        <span class="time-nome">${nomeEsquerda}</span>
                                        ${fEsq}
                                        ${seqEsqHtml}
                                    </div>
                                    <img src="${logoEsquerda}" class="time-logo" onerror="this.style.display='none'">
                                </div>
                                <div class="centro-placar">
                                    <div class="numeros"><span>${placarEsquerda}</span>${separador}<span>${placarDireita}</span></div>
                                    ${penaltisCentroHtml}
                                    <div id="relogio-tela" class="status-jogo" title="${clockDisplay}">${clockDisplay}</div>
                                </div>
                                <div class="time-box fora">
                                    <img src="${logoDireita}" class="time-logo" onerror="this.style.display='none'">
                                    <div class="textos-time fora">
                                        <span class="time-nome">${nomeDireita}</span>
                                        ${fDir}
                                        ${seqDirHtml}
                                    </div>
                                </div>
                            </div>`;
                lastPlacarState = currentPlacarState;
            } else {
                let relogioEl = document.getElementById('relogio-tela');
                if (relogioEl && relogioEl.innerText !== clockDisplay) {
                    relogioEl.innerText = clockDisplay;
                    relogioEl.title = clockDisplay;
                }
            }

            let currentPainelState = JSON.stringify({ esp: jg.esporte, c: jg.escalacaoCasa, f: jg.escalacaoFora, n: jg.lideres_nfl });

            if (currentPainelState !== lastPainelState) {
                document.getElementById('abas-painel').style.display = (jg.esporte === 'futebol') ? 'flex' : 'none';

                if (jg.esporte === "nfl") {
                    const titulo = jg.titulo_destaques || "LÍDERES DO JOGO";
                    const rows = (jg.lideres_nfl || []).map(renderNflLider).join('');
                    painelConteudo.innerHTML = `
                            <div class="nfl-lideres-container">
                                <div class="nfl-lideres-header"><span class="nfl-lideres-titulo">${titulo}</span></div>
                                <div class="nfl-teams-bar"><div class="nfl-team-badge away"><img src="${jg.logoFora}"><span>${jg.abbrevFora || jg.timeFora}</span></div><div class="nfl-team-badge home"><span>${jg.abbrevCasa || jg.timeCasa}</span><img src="${jg.logoCasa}"></div></div>
                                ${rows}
                            </div>`;
                } else if (jg.esporte === "basquete") {
                    let headerEsq = `<span>FORA</span><div class="stats-wrapper"><div class="titulos-stats"><span class="stat-box">PTS</span><span class="stat-box">REB</span><span class="stat-box">AST</span></div><div class="rating-slot"></div></div>`;
                    let headerDir = `<span>CASA</span><div class="stats-wrapper"><div class="titulos-stats"><span class="stat-box">PTS</span><span class="stat-box">REB</span><span class="stat-box">AST</span></div><div class="rating-slot"></div></div>`;
                    let listEsq = "", listDir = "";
                    let srtPts = (a, b) => (parseInt(b.pts) || 0) - (parseInt(a.pts) || 0);
                    if (jg.escalacaoFora) listEsq = [...jg.escalacaoFora].sort(srtPts).map(htmlBasq).join('');
                    if (jg.escalacaoCasa) listDir = [...jg.escalacaoCasa].sort(srtPts).map(htmlBasq).join('');

                    painelConteudo.innerHTML = `
                            <div class="escalacao-grid">
                                <div class="coluna-escalacao casa"><div class="titulo-escalacao">${headerEsq}</div><div>${listEsq}</div></div>
                                <div class="coluna-escalacao fora"><div class="titulo-escalacao">${headerDir}</div><div>${listDir}</div></div>
                            </div>`;
                } else {
                    let titCasa = (jg.escalacaoCasa || []).filter(j => !j.reserva).map(j => htmlFut(j, false)).join('');
                    let resCasa = (jg.escalacaoCasa || []).filter(j => j.reserva).map(j => htmlFut(j, true)).join('');

                    let titFora = (jg.escalacaoFora || []).filter(j => !j.reserva).map(j => htmlFut(j, false)).join('');
                    let resFora = (jg.escalacaoFora || []).filter(j => j.reserva).map(j => htmlFut(j, true)).join('');

                    painelConteudo.innerHTML = `
                            <div class="container-views">
                                <div class="view-titulares">
                                    <div class="escalacao-grid">
                                        <div class="coluna-escalacao casa"><div class="titulo-escalacao">Titulares Casa</div><div>${titCasa}</div></div>
                                        <div class="coluna-escalacao fora"><div class="titulo-escalacao">Titulares Fora</div><div>${titFora}</div></div>
                                    </div>
                                </div>
                                <div class="view-reservas">
                                    <div class="escalacao-grid">
                                        <div class="coluna-escalacao casa"><div class="titulo-escalacao">Reservas Casa</div><div>${resCasa}</div></div>
                                        <div class="coluna-escalacao fora"><div class="titulo-escalacao">Reservas Fora</div><div>${resFora}</div></div>
                                    </div>
                                </div>
                            </div>`;
                }
                lastPainelState = currentPainelState;
            }

            // RENDERIZAÇÃO DA TABELA / GRUPOS E MATA-MATA
            let gruposLista = (jg.grupos && jg.grupos.length > 0) ? jg.grupos : [];
            if (gruposLista.length === 0 && jg.tabela && jg.tabela.length > 0) {
                gruposLista = [{ grupo: "Classificação", ativoPadrao: true, times: jg.tabela }];
            }

            let temGrupos = gruposLista.length > 0;
            let temMataMata = jg.matamata && jg.matamata.length > 0;

            if ((temGrupos || temMataMata) && (jg.esporte === 'futebol' || jg.esporte === 'basquete')) {
                btnTabela.style.display = 'inline-flex';
                if (btnEscalacao) btnEscalacao.style.display = 'inline-flex';

                let idJogoAtual = `${jg.timeCasa}_${jg.timeFora}_${jg.torneio}`;
                if (window.idJogoTabelaIniciado !== idJogoAtual) {
                    window.idJogoTabelaIniciado = idJogoAtual;
                    window.usuarioEscolheuGrupo = false;

                    let tNome = (jg.torneio || "").toLowerCase();
                    let isFaseMata = tNome.includes("knockout") || tNome.includes("playoff") || tNome.includes("eliminat") || tNome.includes("final") || tNome.includes("oitavas") || tNome.includes("quartas");

                    if (temMataMata && (isFaseMata || !temGrupos)) {
                        window.subAbaTabela = 'matamata';
                    } else {
                        window.subAbaTabela = 'grupos';
                    }
                }

                if (!temGrupos && temMataMata) window.subAbaTabela = 'matamata';
                if (temGrupos && !temMataMata) window.subAbaTabela = 'grupos';

                let navTipoHtml = '';
                if (temGrupos && temMataMata) {
                    const labelEliminatorias = (jg.esporte === 'basquete') ? 'Playoffs' : 'Mata-Mata';
                    navTipoHtml = `
        <div class="nav-tipo-tabela">
            <button class="btn-tipo-tab ${window.subAbaTabela === 'grupos' ? 'ativo' : ''}" onclick="event.stopPropagation(); window.trocarSubAba('grupos')">Classificação / Grupos</button>
            <button class="btn-tipo-tab ${window.subAbaTabela === 'matamata' ? 'ativo' : ''}" onclick="event.stopPropagation(); window.trocarSubAba('matamata')">${labelEliminatorias}</button>
        </div>
    `;
                }

                let conteudoFinalHtml = '';

                // 1. ABA DE GRUPOS / CLASSIFICAÇÃO
                if (window.subAbaTabela === 'grupos' && temGrupos) {
                    let idJogoAtual = `${jg.timeCasa}_${jg.timeFora}_${jg.torneio}`;
                    if (window.idJogoTabelaIniciado !== idJogoAtual) {
                        let idxPadrao = gruposLista.findIndex(g => g.ativoPadrao);
                        window.indiceGrupoSelecionado = (idxPadrao !== -1) ? idxPadrao : 0;
                        window.idJogoTabelaIniciado = idJogoAtual;
                        window.usuarioEscolheuGrupo = false;
                    }

                    if (window.indiceGrupoSelecionado >= gruposLista.length) {
                        window.indiceGrupoSelecionado = 0;
                    }

                    let grupoAtual = gruposLista[window.indiceGrupoSelecionado] || gruposLista[0];
                    let totalTimes = (grupoAtual.times || []).length;

                    let seletorGruposHtml = '';
                    if (gruposLista.length > 1) {
                        seletorGruposHtml = `
                                    <div class="container-seletor-grupos">
                                        <button class="btn-seta-scroll" onclick="event.stopPropagation(); document.getElementById('barra-grupos').scrollLeft -= 140;">‹</button>
                                        <div class="seletor-grupos-bar" id="barra-grupos">` +
                            gruposLista.map((g, idx) => {
                                let cl = (idx === window.indiceGrupoSelecionado) ? 'ativo' : '';
                                return `<button class="btn-grupo-pill ${cl}" onclick="event.stopPropagation(); window.trocarGrupo(${idx})">${g.grupo}</button>`;
                            }).join('') +
                            `</div>
                                        <button class="btn-seta-scroll" onclick="event.stopPropagation(); document.getElementById('barra-grupos').scrollLeft += 140;">›</button>
                                    </div>`;
                    }

                    // IDENTIFICAÇÃO DINÂMICA DA COR BASE DO TORNEIO
                    const COR_TORNEIO = (() => {
                        const tor = (jg.torneio || "").toLowerCase();
                        if (tor.includes("europa")) return 'pos-uel';
                        if (tor.includes("conference")) return 'pos-conference';
                        if (tor.includes("libertadores")) return 'pos-libertadores';
                        return 'pos-ucl';
                    })();

                    const MAPA_DOTS = {
                        'pos-ucl': 'ucl',
                        'pos-uel': 'uel',
                        'pos-conference': 'conf',
                        'pos-libertadores': 'lib',
                        'pos-playoff': 'playoff',
                        'pos-pre-lib': 'pre',
                        'pos-sula': 'sula',
                        'pos-rebaixamento': 'z4'
                    };

                    function obterZonaClass(pos, promocao) {
                        const p = (promocao || "").trim().toLowerCase();
                        const tor = (jg.torneio || "").toLowerCase();
                        const isTorneioEuropeu = tor.includes("champions") || tor.includes("europa") || tor.includes("conference") || tor.includes("uefa");
                        const isCopa = isTorneioEuropeu || tor.includes("libertadores") || tor.includes("sudamericana") || tor.includes("copa");

                        // Suporte específico a Basquetebol (NBA, Euroliga, NBB)
                        if (jg.esporte === 'basquete') {
                            if (p.includes("play-in") || p.includes("play in")) return 'pos-playoff';
                            if (p.includes("playoff") || p.includes("quarter") || p.includes("oitavas")) return 'pos-uel';
                            // Fallback padrão NBA (1º ao 6º direto, 7º ao 10º Play-in)
                            if (!p && totalTimes >= 10) {
                                if (pos <= 6) return 'pos-uel';
                                if (pos <= 10) return 'pos-playoff';
                            }
                            return (pos <= 8) ? 'pos-uel' : 'pos-neutra';
                        }

                        if (!p) {
                            if (totalTimes <= 4 && pos <= 2) return COR_TORNEIO;
                            return 'pos-neutra';
                        }

                        if (!isCopa && /relegat|rebaixa|descens|z-?4/.test(p)) {
                            return 'pos-rebaixamento';
                        }

                        if (/conference|uecl/.test(p)) return 'pos-conference';
                        if (/europa league|\buel\b/.test(p)) return 'pos-uel';
                        if (/sudamericana|sul-americana/.test(p)) return 'pos-sula';
                        if (/libertadores/.test(p)) return 'pos-libertadores';
                        if (/champions/.test(p)) return 'pos-ucl';

                        if (/qualif|knockout|pre|pré/.test(p) || (p.includes("playoff") && pos > 8)) {
                            return 'pos-playoff';
                        }

                        if (totalTimes <= 4) {
                            return (pos <= 2) ? COR_TORNEIO : 'pos-neutra';
                        }

                        return COR_TORNEIO;
                    }

                    let promocoesUnicas = [];
                    (grupoAtual.times || []).forEach(t => {
                        if (t.promocao && !promocoesUnicas.some(x => x.texto === t.promocao)) {
                            const corClasse = obterZonaClass(t.pos, t.promocao);
                            if (corClasse !== 'pos-neutra') {
                                promocoesUnicas.push({
                                    texto: t.promocao,
                                    dot: MAPA_DOTS[corClasse] || 'neutro'
                                });
                            }
                        }
                    });

                    let legendaHtml = '';
                    if (promocoesUnicas.length > 0) {
                        legendaHtml = `<div class="legenda-tabela">${promocoesUnicas.map(item => `<span class="legenda-item"><span class="legenda-dot ${item.dot}"></span>${item.texto}</span>`).join('')}</div>`;
                    }

                    const isBasq = (jg.esporte === 'basquete');
                    const temPct = (grupoAtual.times || []).some(t => Boolean(t.pct));

                    let rowsHtml = (grupoAtual.times || []).map(t => {
                        let clDestaque = (t.isCasa || t.isFora) ? 'time-destaque-jogo' : '';
                        let clZona = obterZonaClass(t.pos, t.promocao);
                        let logoHtml = t.logo ? `<img src="${t.logo}" class="tab-logo-time" onerror="this.style.display='none'">` : '';

                        let varHtml = '<span class="var-pos var-neutro">•</span>';
                        if (t.variacao > 0) {
                            varHtml = `<span class="var-pos var-subiu" title="Subiu ${t.variacao} posições">▲${t.variacao}</span>`;
                        } else if (t.variacao < 0) {
                            varHtml = `<span class="var-pos var-desceu" title="Desceu ${Math.abs(t.variacao)} posições">▼${Math.abs(t.variacao)}</span>`;
                        }

                        // Colunas específicas: basquete não tem empates e exibe PCT / Diferença
                        let colunasStatsHtml = isBasq ? `
                                    <td class="tab-num">${t.jogos}</td>
                                    <td class="tab-num">${t.v}</td>
                                    <td class="tab-num">${t.d}</td>
                                    <td class="tab-num">${t.sg}</td>
                                    <td class="tab-pts">${temPct ? t.pct : t.pts}</td>
                                ` : `
                                    <td class="tab-num">${t.jogos}</td>
                                    <td class="tab-num">${t.v}</td>
                                    <td class="tab-num">${t.e}</td>
                                    <td class="tab-num">${t.d}</td>
                                    <td class="tab-num">${t.sg}</td>
                                    <td class="tab-pts">${t.pts}</td>
                                `;

                        return `
                                    <tr class="${clDestaque}">
                                        <td class="col-tab-pos">
                                            <div class="pos-container">
                                                <span class="pos-badge ${clZona}">${t.pos}</span>
                                                ${varHtml}
                                            </div>
                                        </td>
                                        <td class="col-tab-time">${logoHtml}<span>${t.nome}</span></td>
                                        ${colunasStatsHtml}
                                    </tr>
                                `;
                    }).join('');

                    let theadHtml = isBasq ? `
                                <thead>
                                    <tr>
                                        <th class="col-tab-pos">#</th>
                                        <th style="text-align: left; padding-left: 6px;">EQUIPA</th>
                                        <th title="Jogos">J</th>
                                        <th title="Vitórias">V</th>
                                        <th title="Derrotas">D</th>
                                        <th title="Diferença de Pontos">+/-</th>
                                        <th class="tab-pts" title="${temPct ? 'Aproveitamento' : 'Pontos'}">${temPct ? 'PCT' : 'PTS'}</th>
                                    </tr>
                                </thead>
                            ` : `
                                <thead>
                                    <tr>
                                        <th class="col-tab-pos">#</th>
                                        <th style="text-align: left; padding-left: 6px;">CLUBE</th>
                                        <th title="Jogos">J</th>
                                        <th title="Vitórias">V</th>
                                        <th title="Empates">E</th>
                                        <th title="Derrotas">D</th>
                                        <th title="Saldo de Gols">SG</th>
                                        <th class="tab-pts" title="Pontos">PTS</th>
                                    </tr>
                                </thead>
                            `;

                    conteudoFinalHtml = `
                                ${seletorGruposHtml}
                                <table class="tabela-classificacao">
                                    ${theadHtml}
                                    <tbody>${rowsHtml}</tbody>
                                </table>
                                ${legendaHtml}
                            `;
                }
                // 2. ABA DE MATA-MATA
                else if (window.subAbaTabela === 'matamata' && temMataMata) {
                    let fasesHtml = jg.matamata.map(f => {
                        let cardsJogos = f.jogos.map(m => {
                            let clAtual = m.isJogoAtual ? 'jogo-atual' : '';
                            let l1 = m.logo1 ? `<img src="${m.logo1}" class="logo-time-mata" onerror="this.style.display='none'">` : '';
                            let l2 = m.logo2 ? `<img src="${m.logo2}" class="logo-time-mata" onerror="this.style.display='none'">` : '';
                            let pen1Html = (m.pen1 !== undefined && m.pen1 !== null) ? `<span class="score-pen-mata">(${m.pen1})</span>` : '';
                            let pen2Html = (m.pen2 !== undefined && m.pen2 !== null) ? `<span class="score-pen-mata">(${m.pen2})</span>` : '';

                            const isBasq = (jg.esporte === 'basquete');

                            // Identificação textual de série no rodapé
                            let statusTexto = m.status || '';
                            if (isBasq && m.placar1 !== '-' && m.placar2 !== '-') {
                                if (!statusTexto.toLowerCase().includes('série')) {
                                    statusTexto = `${statusTexto}`;
                                }
                            }

                            return `
        <div class="card-confronto ${clAtual}">
            <div class="linha-time-mata">
                <div class="info-time-mata">${l1}<span>${m.time1}</span></div>
                <div class="score-box-mata">
                    <span class="score-mata" title="${isBasq ? 'Vitórias na série' : 'Gols'}">${m.placar1}</span>
                    ${pen1Html}
                </div>
            </div>
            <div class="linha-time-mata">
                <div class="info-time-mata">${l2}<span>${m.time2}</span></div>
                <div class="score-box-mata">
                    <span class="score-mata" title="${isBasq ? 'Vitórias na série' : 'Gols'}">${m.placar2}</span>
                    ${pen2Html}
                </div>
            </div>
            <div style="display: flex; align-items: center; justify-content: ${isBasq ? 'space-between' : 'flex-end'}; margin-top: 3px;">
                ${isBasq ? '<span class="badge-serie-tag">SÉRIE</span>' : ''}
                ${statusTexto ? `<div class="status-rodape-mata" style="margin-top: 0;">${statusTexto}</div>` : ''}
            </div>
        </div>
    `;
                        }).join('');

                        return `
                                    <div class="bloco-fase">
                                        <div class="titulo-fase-mata">${f.fase}</div>
                                        <div class="grid-jogos-mata">${cardsJogos}</div>
                                    </div>
                                `;
                    }).join('');

                    conteudoFinalHtml = `<div class="container-matamata">${fasesHtml}</div>`;
                }

                // TRAVA DE ESTADO COM PRESERVAÇÃO DE SCROLL DOS GRUPOS
                let currentTabelaState = JSON.stringify({
                    sub: window.subAbaTabela,
                    grpIdx: window.indiceGrupoSelecionado,
                    grupos: jg.grupos,
                    tabela: jg.tabela,
                    matamata: jg.matamata
                });

                if (currentTabelaState !== lastTabelaState) {
                    const barraAntiga = document.getElementById('barra-grupos');
                    const scrollSalvo = barraAntiga ? barraAntiga.scrollLeft : null;

                    document.getElementById('conteudo-tabela').innerHTML = navTipoHtml + conteudoFinalHtml;
                    lastTabelaState = currentTabelaState;

                    if (window.subAbaTabela === 'grupos') {
                        const barraNova = document.getElementById('barra-grupos');
                        if (barraNova) {
                            if (scrollSalvo !== null) barraNova.scrollLeft = scrollSalvo;
                            const btnAtivo = barraNova.querySelector('.btn-grupo-pill.ativo');
                            if (btnAtivo) btnAtivo.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
                        }
                    } else if (window.subAbaTabela === 'matamata') {
                        // Rola automaticamente a tabela até o confronto da transmissão (ex: Quartas/Semi/Final)
                        const cardJogoAtual = document.querySelector('.card-confronto.jogo-atual');
                        if (cardJogoAtual) {
                            cardJogoAtual.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        }
                    }
                }

            } else {
                btnTabela.style.display = 'none';
                if (btnEscalacao) btnEscalacao.style.display = 'none';
            }

            if (btnEscalacao) {
                const txtBtn = (jg.esporte === 'basquete') ? 'BOX SCORE' : 'ESCALAÇÃO';
                const spanBtn = btnEscalacao.querySelector('span');
                if (spanBtn) spanBtn.innerText = txtBtn;
                btnEscalacao.title = (jg.esporte === 'basquete') ? 'Ver Box Score' : 'Ver Escalação';
            }
        }
    } catch (e) {
        console.error("Erro ao aplicar dados na tela:", e);
    }
}

const mediaShowcase = document.getElementById('media-showcase');
const cardPrincipal = document.getElementById('card-principal');
mediaShowcase.addEventListener('click', fecharMedia);
window.addEventListener('keydown', (e) => { if (e.key === 'Escape') fecharMedia(); });

function fecharMedia() {
    mediaShowcase.classList.remove('show');
    mediaShowcase.innerHTML = '';
    cardPrincipal.style.display = 'flex';
}

function mostrarImagem(url) {
    cardPrincipal.style.display = 'none';
    mediaShowcase.innerHTML = '';
    const img = document.createElement('img');
    img.src = url; img.alt = 'Print Screen';
    img.addEventListener('click', (e) => e.stopPropagation());
    mediaShowcase.appendChild(img);
    mediaShowcase.classList.add('show');
}

function mostrarTweet(tweetUrl) {
    cardPrincipal.style.display = 'none';
    mediaShowcase.innerHTML = '';
    const wrapper = document.createElement('div');
    wrapper.className = 'tweet-card-wrapper';
    wrapper.addEventListener('click', (e) => e.stopPropagation());
    wrapper.innerHTML = `<blockquote class="twitter-tweet" data-dnt="true" data-theme="dark" data-conversation="none" data-align="center"><a href="${tweetUrl}"></a></blockquote>`;
    mediaShowcase.appendChild(wrapper);
    mediaShowcase.classList.add('show');
    const permitirFullscreen = () => {
        wrapper.querySelectorAll('iframe').forEach(f => { f.setAttribute('allowfullscreen', 'true'); f.setAttribute('allow', 'autoplay; fullscreen'); });
    };
    if (!window.twttr) {
        const scriptTw = document.createElement('script');
        scriptTw.src = "https://platform.twitter.com/widgets.js";
        scriptTw.async = true;
        scriptTw.onload = () => { setTimeout(permitirFullscreen, 400); setTimeout(permitirFullscreen, 1200); };
        document.body.appendChild(scriptTw);
    } else {
        window.twttr.widgets.load(wrapper);
        setTimeout(permitirFullscreen, 400); setTimeout(permitirFullscreen, 1200);
    }
}

window.addEventListener('paste', (e) => {
    const items = (e.clipboardData || e.originalEvent.clipboardData).items;
    let colouImagem = false;
    for (let index in items) {
        const item = items[index];
        if (item.kind === 'file' && item.type.startsWith('image/')) {
            mostrarImagem(URL.createObjectURL(item.getAsFile()));
            colouImagem = true; break;
        } else if (item.kind === 'string' && item.type === 'text/plain') {
            item.getAsString((text) => {
                if (!colouImagem && (text.includes('twitter.com') || text.includes('x.com'))) {
                    const match = text.match(/https?:\/\/(?:www\.)?(?:twitter\.com|x\.com)\/([a-zA-Z0-9_]+)\/status\/([0-9]+)/i);
                    if (match) mostrarTweet(`https://twitter.com/${match[1]}/status/${match[2]}`);
                }
            });
        }
    }
});

buscarDadosServidor();
setInterval(buscarDadosServidor, 1000);
setInterval(processarFilaAntiSpoiler, 500);

setInterval(() => {
    if (relogioRodando && !animando && document.getElementById('card-principal').classList.contains('futebol')) {
        segundosLocais++;
        if (segundosLocais >= 60) { segundosLocais = 0; minutosLocais++; }
        let el = document.getElementById('relogio-tela');
        if (el && el.innerText !== "") el.innerText = `${minutosLocais}:${segundosLocais.toString().padStart(2, '0')}`;
    }
}, 1000);

(function configurarPiP() {
    const btnPip = document.getElementById('btn-pip');
    if (!btnPip) return;

    const isOBS = !!(window.obsstudio || navigator.userAgent.includes("OBS"));
    const suportaDocPiP = 'documentPictureInPicture' in window;

    if (isOBS || !suportaDocPiP) {
        btnPip.style.display = 'none';
        return;
    }

    btnPip.style.display = 'flex';

    const originalGetElementById = document.getElementById.bind(document);
    document.getElementById = function (id) {
        let el = originalGetElementById(id);
        if (!el && window._pipWindow && !window._pipWindow.closed) {
            el = window._pipWindow.document.getElementById(id);
        }
        return el;
    };

    btnPip.addEventListener('click', async () => {
        if (window._pipWindow && !window._pipWindow.closed) {
            window._pipWindow.close();
            return;
        }

        try {
            const pipWindow = await window.documentPictureInPicture.requestWindow({
                width: 660,
                height: 380
            });
            window._pipWindow = pipWindow;

            [...document.querySelectorAll('link[rel="stylesheet"], style')].forEach((node) => {
                pipWindow.document.head.appendChild(node.cloneNode(true));
            });

            pipWindow.document.body.style.cssText = `
                        margin: 0;
                        padding: 12px;
                        background: #080c18;
                        display: flex;
                        flex-direction: column;
                        justify-content: center;
                        align-items: center;
                        min-height: 100vh;
                        box-sizing: border-box;
                        overflow-x: hidden;
                    `;

            const card = document.getElementById('card-principal');
            const containerPai = card.parentNode;
            pipWindow.document.body.appendChild(card);

            btnPip.querySelector('span').innerText = "Fechar PiP";

            pipWindow.addEventListener('keydown', (e) => {
                window.dispatchEvent(new KeyboardEvent('keydown', {
                    key: e.key,
                    code: e.code,
                    bubbles: true
                }));
            });

            pipWindow.addEventListener('pagehide', () => {
                containerPai.appendChild(card);
                window._pipWindow = null;
                btnPip.querySelector('span').innerText = "Mini Placar (PiP)";
            });

        } catch (err) {
            console.error("Falha ao abrir o modo Picture-in-Picture:", err);
        }
    });
})();