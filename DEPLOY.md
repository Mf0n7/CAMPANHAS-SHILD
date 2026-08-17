# Deploy no Coolify

Um container só. O FastAPI serve a API e as telas na mesma porta — **não existe frontend
separado**, então não há rota de frontend/backend para configurar: aponte o domínio para
a porta `8010` e pronto.

**Sem volume.** Poster, texto da campanha e status de disparo ficam todos no Postgres.
O que o container escreve em disco é só cache descartável (as imagens montadas do WhatsApp),
que se refaz sozinho se sumir. Pode redeployar à vontade.

---

## 1. Postgres

No Coolify: **+ New → Database → PostgreSQL**. Depois de criar, copie a **Internal URL**
(algo como `postgres://postgres:senha@nome-do-servico:5432/postgres`).

Não precisa criar tabela nenhuma — o sistema cria na primeira subida.

## 2. Conta de serviço do Google

A planilha é privada, então o servidor precisa de uma identidade própria. Isso é feito
uma vez:

1. <https://console.cloud.google.com> → crie um projeto (ou use um existente)
2. **APIs e serviços → Biblioteca** → ative **Google Sheets API**
3. **IAM e administrador → Contas de serviço → Criar conta de serviço**
   - nome: `campanhas-shild` (o que quiser)
   - não precisa dar papel nenhum no projeto
4. Na conta criada → aba **Chaves → Adicionar chave → Criar nova → JSON**. Baixa um arquivo.
5. Abra o JSON e copie o valor de `client_email`
   (algo como `campanhas-shild@seu-projeto.iam.gserviceaccount.com`)
6. **Na planilha**: Compartilhar → cole esse email → permissão **Editor** → Enviar

> **Editor**, não Leitor: é o que permite salvar as correções que você faz pela tela.

O conteúdo **inteiro** do JSON vai em `GOOGLE_CREDENTIALS_JSON`. Cole numa linha só —
o sistema já lida com as quebras de linha escapadas da chave privada.

## 3. Aplicação

No Coolify: **+ New → Application → Public/Private Repository** (ou Docker Compose,
apontando para o `docker-compose.yml` do repositório).

- **Build Pack**: Dockerfile
- **Port**: `8010`
- **Health check path**: `/saude`
- **Domain**: o domínio que você quiser

Cole as variáveis de ambiente (seção 4). Deploy.

## 4. Variáveis de ambiente

Obrigatórias:

| Variável | O que é |
|---|---|
| `DATABASE_URL` | Internal URL do Postgres criado no passo 1 |
| `SHEET_ID` | URL (ou ID) da planilha de funcionários |
| `GOOGLE_CREDENTIALS_JSON` | JSON inteiro da conta de serviço, numa linha |

Email (Brevo):

| Variável | Valor |
|---|---|
| `BREVO_API_KEY` | `xkeysib-...` — necessária para ler aberturas e cliques |
| `BREVO_SMTP_LOGIN` | login SMTP (Brevo → SMTP & API → aba SMTP) |
| `BREVO_SMTP_KEY` | `xsmtpsib-...` — é o que faz o poster aparecer **dentro** do email |
| `MAIL_FROM_DOMAIN` | `shild.click` |
| `MAIL_FROM_PREFIX` | `comunicados` |
| `MAIL_FROM_NAME` | `Comunicados {empresa}` |
| `MAIL_REPLY_TO` | para onde vão as respostas |
| `MAIL_UNSUBSCRIBE_EMAIL` | descadastro no rodapé |
| `MAIL_TEST_TO` | seu email, preenche o campo de teste |
| `CAMPAIGN_TAG` | troque a cada campanha nova |

WhatsApp (Evolution API):

| Variável | Valor |
|---|---|
| `EVOLUTION_API_URL` | URL da sua instância |
| `EVOLUTION_API_KEY` | token **da instância**, não o global |
| `EVOLUTION_INSTANCE` | nome da instância |
| `WA_DELAY_SECONDS` | `8` — não abaixe muito |

Opcionais com padrão razoável: `SHEET_TAB` (vazio = primeira aba), `SHEET_HEADER_ROW` (`5`),
`TRANSPORTE` (`auto`), `MAIL_FROM_PER_EMPRESA` (`0`), `SEND_DELAY_SECONDS` (`1.5`),
`WA_DDD_PADRAO`, `EMAIL_LOGO_URL`, `SHILD_SITE_URL`, `INSTAGRAM_URL`.

A lista completa e comentada está em [.env.example](.env.example).

## 5. Conferir se subiu certo

1. `https://seu-dominio/saude` → deve responder `{"ok":true,"banco":"PostgreSQL 16..."}`
2. Abra a tela. No passo 3 deve aparecer em verde o nome da planilha, a aba e as colunas lidas
3. Clique **Sincronizar com a planilha** — deve trazer a contagem de funcionários
4. Envie um teste por email e um por WhatsApp

Se o passo 2 vier em vermelho com "Sem acesso à planilha", a planilha ainda não foi
compartilhada com o `client_email` da conta de serviço — a mensagem mostra qual é.

---

## Rodar na sua máquina

Continua funcionando sem Docker e sem Postgres: com `DATABASE_URL` vazio o sistema usa
um SQLite local em `saidas/campanhas.db`.

```powershell
cd "C:\Users\Matheus Fontenele\Documents\projetos\SHILD\shild-system\RSPV capaign"
.\venv\Scripts\python.exe run.py
```

Para o acesso à planilha localmente, baixe o JSON da conta de serviço e aponte
`GOOGLE_CREDENTIALS_FILE=C:\caminho\para\chave.json` no `.env` (mais prático que colar
o JSON inteiro).

## Segurança

O sistema **não tem login**. Quem abrir a URL dispara campanha e edita a planilha.
Não exponha num domínio público sem proteção — no Coolify, ative autenticação básica
no proxy, ou deixe acessível só por rede interna/VPN.
