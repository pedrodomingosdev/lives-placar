## ⚙️ Pré-requisitos

* **Sistema Operativo:** Windows 10 ou Windows 11[cite: 11].
* **Python:** Versão 3.8 ou superior instalada e adicionada ao `PATH` do sistema[cite: 11].
* **Navegador:** Google Chrome instalado no diretório padrão[cite: 11].
* **OBS Studio:** Para inclusão da fonte de navegador[cite: 13].

---

## 🚀 Como Executar

1. Descarregue ou clone este repositório para o seu computador.
2. Dê duplo clique no ficheiro `INICIAR_PLACAR.bat`[cite: 11].
3. O script irá automaticamente:
   * Verificar se existem versões mais recentes de `scraper.py` e `placar.html` no GitHub e atualizá-los[cite: 11].
   * Instalar as dependências necessárias (`selenium`, `webdriver-manager`)[cite: 11].
   * Abrir uma janela isolada do Google Chrome na porta de depuração `9333` (sem fechar o seu Chrome pessoal)[cite: 11, 13].
   * Iniciar o servidor HTTP local na porta `8000`[cite: 13].
4. No Chrome isolado aberto pelo inicializador, aceda à página do jogo pretendido no Sofascore ou na ESPN[cite: 13].
5. O terminal iniciará a leitura contínua dos dados em segundo plano[cite: 11, 13].

---

## 🎥 Configuração no OBS Studio

1. No OBS Studio, adicione uma nova fonte do tipo **Navegador** (*Browser Source*)[cite: 13].
2. No campo **URL**, introduza[cite: 12, 13]:
   ```text
   http://localhost:8000/placar.html
3. **Defina as dimensões da fonte:**
   * **Largura:** `800` (ou `1920` se preferir posicionamento livre em tela cheia)
   * **Altura:** `800`
4. **Marque a opção:**
   * ☑ **Atualizar o navegador quando a cena se tornar ativa**