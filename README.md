## ⚙️ Pré-requisitos

* **Sistema Operativo:** Windows 10 ou Windows 11.
* **Python:** Versão 3.8 ou superior instalada e adicionada ao `PATH` do sistema.
* **Navegador:** Google Chrome instalado no diretório padrão.
* **OBS Studio:** Para inclusão da fonte de navegador.

---

## 🚀 Como Executar

1. Descarregue ou clone este repositório para o seu computador.
2. Dê duplo clique no ficheiro `INICIAR_PLACAR.bat`.
3. O script irá automaticamente:
   * Verificar se existem versões mais recentes de `scraper.py` e `placar.html` no GitHub e atualizá-los.
   * Instalar as dependências necessárias (`selenium`, `webdriver-manager`).
   * Abrir uma janela isolada do Google Chrome na porta de depuração `9333` (sem fechar o seu Chrome pessoal).
   * Iniciar o servidor HTTP local na porta `8000`.
4. No Chrome isolado aberto pelo inicializador, aceda à página do jogo pretendido no Sofascore ou na ESPN.
5. O terminal iniciará a leitura contínua dos dados em segundo plano.

---

## 🎥 Configuração no OBS Studio

1. No OBS Studio, adicione uma nova fonte do tipo **Navegador** (*Browser Source*).
2. No campo **URL**, introduza:
   ```text
   http://localhost:8000/placar.html
3. **Defina as dimensões da fonte:**
   * **Largura:** `800` (ou `1920` se preferir posicionamento livre em tela cheia)
   * **Altura:** `800`
4. **Marque a opção:**
   * ☑ **Atualizar o navegador quando a cena se tornar ativa**