# 🔐 Cofre de Toxinas — Ministério do Meio Ambiente

Sistema de controle de acesso a um cofre de segurança máxima do **Ministério do Meio Ambiente**, onde são guardados os segredos mais sensíveis sobre o uso de toxinas, com autenticação biométrica facial e auditoria em tempo real, desenvolvido em Python utilizando Streamlit e DeepFace.

O sistema é a última linha de defesa contra quem tentar obter essas informações a qualquer custo: apenas pessoas devidamente autorizadas conseguem abrir os compartimentos do cofre, com base em um rigoroso esquema de permissões dividido em **três níveis de segurança**.

---

## 🛠️ Tecnologias Utilizadas

* **Linguagem:** Python 3.12
* **Interface Web:** Streamlit
* **Banco de Dados:** SQLite3
* **Visão Computacional:** DeepFace (Modelo VGG-Face / Métrica Cosine)
* **Processamento de Dados:** Pandas / Altair

---

## 🔐 Níveis de Acesso (cumulativos)

Um colaborador de nível **N** acessa todos os compartimentos dos níveis anteriores (1 a N).

| Nível | Nome | Acesso ao cofre |
|---|---|---|
| 1 | Permissão Geral | Catálogo público de toxinas e informações gerais (indivíduos com permissão geral). |
| 2 | Diretor de Divisões Específicas | Inventário, localização nos compartimentos e conservação das toxinas (diretores de divisões específicas). |
| 3 | Ministro do Meio Ambiente | Dossiê completo, movimentações, cadeia de custódia, gestão e auditoria do cofre (acesso exclusivo). |

---

## 🔑 Credenciais e Permissões do Sistema

### Home / tela inicial (pré-login)

Antes do login, o sistema exibe a **home** com a imagem (capa) salva na pasta
`IMAGEMHOME/`. Sobre a imagem há **máscaras invisíveis** (camadas clicáveis
transparentes) posicionadas sobre os elementos desenhados:

* **Usuário e Senha** — campo do formulário de login: abre o login (usuário/senha).
* **Acesso** — abre direto a **validação biométrica** (colaboradores com cadastro
  entram conforme o nível, sem senha).
* **Cadastro** — abre o login e, após autenticar, encaminha à aba de cadastro
  **apenas** quem possui a **permissão de cadastro** (`pode_cadastrar`). Sem ela, o
  colaborador é redirecionado ao cofre com aviso.
* **Criar Primeiro Administrador** (somente quando não há credenciais) — primeiro acesso.

As máscaras escalam com a imagem (posições em porcentagem), mantendo o alinhamento
em qualquer tamanho de tela.

> **Ajuste das máscaras:** no rodapé da home há o link **⚙️ Ajustar áreas clicáveis**.
> Ele abre um modo com a imagem e **bordas tracejadas** sobre cada máscara, com
> controles X/Y/Largura/Altura para alinhá-las aos elementos. Clique em
> **💾 Salvar posições** para gravar (fica salvo no banco, tabela `configuracoes`,
> chaves `home_zona_*`). Se a pasta `IMAGEMHOME/` estiver vazia, a home exibe os
> botões textuais como fallback.

### Login obrigatório (usuário e senha)

O acesso a **todas** as áreas do aplicativo exige autenticação (usuário/senha ou
biometria; senhas armazenadas com hash PBKDF2 + salt — nunca em texto puro). Sem
login, o aplicativo exibe apenas a home/tela de entrada e nenhum dado é renderizado.

### Colaboradores já cadastrados (sem credenciais)

Colaboradores cadastrados **antes** do esquema de credenciais (com foto/biometria)
continuam acessando o sistema pelo botão **🔐 Acesso** da home, que abre a tela
**📹 Validação Biométrica**: ao reconhecer o rosto, a sessão é iniciada e as
permissões por nível são aplicadas normalmente. O nível 3 pode depois definir
usuário/senha para eles na aba 🛡️ **Gestão de Acessos**.

### Restrições por tela

| Tela | Permissão exigida |
|---|---|
| 🔐 Cofre de Toxinas do MMA | Sessão autenticada (níveis cumulativos por compartimento) |
| 📹 Validar Acesso / Login Biométrico | Sessão autenticada |
| 📈 Dashboard Analítico de Acessos | Nível 2 ou 3 |
| 📊 Dashboard e Relatórios | Nível 2 ou 3 |
| 🐞 Registro de Erros / Logs | Nível 2 ou 3 |
| 📸 Cadastro de Colaboradores | Sessão autenticada **e** permissão de cadastro (`pode_cadastrar`) |
| 🛡️ Gestão de Acessos | Nível 3 (Ministro) |

A **permissão de cadastro** é concedida pelo próprio sistema (nível 3) a apenas
**1 ou 2 colaboradores de confiança** por meio da aba **🛡️ Gestão de Acessos**,
que também cria/altera usuários, redefine senhas e ajusta o nível de acesso de
cada colaborador.

---

## ⚙️ Arquitetura e Funcionalidades

* **🔐 Cofre de Toxinas do MMA:** Painel do cofre com 3 compartimentos protegidos por nível (catálogo → inventário → dossiê/governança), com KPIs e exportação CSV. Exige sessão ativa (login biométrico).
* **📸 Cadastro de Colaboradores:** Registro de novos usuários com foto (webcam ou upload), cargo, **divisão do Ministério**, nível de acesso (1–3) e **credenciais de login** (usuário/senha). **Restrito** a colaboradores com permissão de cadastro concedida pelo nível 3.
* **📹 Validação Biométrica / Login:** Reconhecimento facial (métrica Cosine) que libera apenas os compartimentos permitidos pelo nível do colaborador e inicia a sessão. Inclui o modo **🎥 Mini Vídeo Anti-Fraude** com 6 barreiras anti-spoofing:
  * **Janela mínima de 2s** de captura (4–8 quadros);
  * **Movimento** entre os quadros;
  * **Padrão orgânico** da variação temporal (foto deslizando = padrão rígido);
  * **Variação 3D (parallax)** de nariz/olhos/boca — bloqueia translação plana de foto;
  * **Piscada obrigatória** via EAR (68 landmarks dlib);
  * **Detecção de tela/Moiré** (FFT) para vídeo pré-gravado no celular.
  * **Bloqueio temporário por compartimento:** 3 tentativas de fraude/negação em 10 min travam a validação por 15 min. **Sessão expira por inatividade (5 min)**.
* **📈 Dashboard Analítico de Acessos:** Tendências temporais, distribuição por compartimento, equipe do cofre (colaboradores por nível/divisão), diagnósticos de segurança e auditoria. Permite **exportar relatório PDF** com os filtros ativos e gráficos ilustrativos. **Restrito a níveis 2 e 3.**
* **📊 Dashboard e Relatórios:** Métricas de acessos (Permitidos vs. Negados), filtros, exportação em CSV e **relatório PDF completo** com KPIs, gráficos e tabelas de auditoria. **Restrito a níveis 2 e 3.**
* **🛡️ Gestão de Acessos (nível 3):** Cria/altera usuários, redefine senhas, ajusta níveis e concede a **permissão de cadastro** a 1–2 colaboradores de confiança.
* **🐞 Registro de Erros / Logs:** Captura automática de erros com explicação amigável e sugestão de solução.

---


## 📁 Estrutura do Projeto

* `app.py` — Código principal da aplicação Streamlit.
* `controle_acesso.db` — Banco de dados SQLite (colaboradores, divisões, níveis de acesso e logs). **Não é versionado**: é criado automaticamente na primeira execução.
* `fotos_cadastradas/` — Diretório local para armazenamento das imagens de cadastro (não versionado).
* `IMAGEMHOME/` — Imagem ilustrativa usada como capa da home (primeira imagem encontrada).
* `gerar_excel.py` — Gerador de relatório executivo em Excel com base em dados de exemplo.
* `requirements.txt` — Dependências Python do projeto.
* `documentacao_cofre_toxinas.*` — Documentação do sistema (DOCX/HTML/PDF).
* `documentacao_projeto_reconhecimento.*` — Documentação consolidada do projeto (DOCX/PDF).
* `diagrama_fluxo_geral.png` — Diagrama do fluxo geral do sistema.
* `diagrama_niveis_auditoria.png` — Diagrama dos níveis de acesso e auditoria.
* `.streamlit/config.toml` — Configurações do servidor Streamlit.
* `.gitignore` — Arquivos locais excluídos do versionamento (banco, `venv/`, relatórios gerados).
* `venv/` — Ambiente virtual Python (não versionado).

---

## 🚀 Como Executar o Projeto

1. **Criar/ativar o ambiente virtual e instalar dependências:**
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
   *(Necessário: Python 3.12.)*
2. **Iniciar a aplicação:**
   ```bash
   streamlit run app.py
   ```
3. **Para gerar o relatório Excel:** executar `python gerar_excel.py`.

---

## 🧬 Modelo de Dados

* `colaboradores` — `id, nome, cargo, divisao, nivel_acesso (1–3), usuario (login), senha_hash (PBKDF2+salt), pode_cadastrar (0/1), foto_path, data_cadastro`
* `logs_acesso` — `id, colaborador_nome, setor (compartimento solicitado), data_hora, status (PERMITIDO/NEGADO)`
* `logs_erros` — `id, data_hora, tipo, modulo, mensagem, descricao, sugerida`
* `tentativas_seguranca` — `id, compartimento, data_hora, motivo, detalhes, origem` (registra fraudes e negativas que acionam o bloqueio temporário)
* `configuracoes` — `chave, valor` (persiste preferências do sistema, como as zonas clicáveis da home)

> Os colaboradores previamente cadastrados foram reiniciados para o **Nível 1 (Permissão Geral)** na migração para o novo esquema de segurança do cofre.
## 📄 Exportação em PDF

O app gera relatórios PDF ilustrativos com KPIs, gráficos (Altair) e tabelas:

* No **📈 Dashboard Analítico** — botão "Baixar Relatório PDF (Dados Filtrados + Gráficos)": respeita os filtros ativos da tela.
* No **📊 Dashboard e Relatórios** — botão "Baixar Relatório PDF (Completo + Gráficos)": relatório geral com todos os dados.

Dependências: `fpdf2` (gera o PDF) e `vl-convert-python` (renderiza os gráficos Altair em PNG).
