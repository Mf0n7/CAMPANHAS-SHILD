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

### Como passar a credencial

Três formas, escolha uma:

| Forma | Variáveis | Quando usar |
|---|---|---|
| **A** | `GOOGLE_SA_EMAIL` + `GOOGLE_SA_PRIVATE_KEY` | **Coolify** — só dois campos, tirados do JSON |
| **B** | `GOOGLE_CREDENTIALS_JSON` | o JSON inteiro numa linha |
| **C** | `GOOGLE_CREDENTIALS_FILE` | no seu PC, aponta o caminho do arquivo |

Na forma A, abra o JSON baixado e copie dois campos:

```json
{
  "client_email": "campanhas-shild@seu-projeto.iam.gserviceaccount.com",  ← GOOGLE_SA_EMAIL
  "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEv...\n-----END PRIVATE KEY-----\n"  ← GOOGLE_SA_PRIVATE_KEY
}
```

A chave pode ser colada com `\n` literal, entre aspas ou numa linha só sem separador
nenhum — o sistema reconstrói o PEM.

> **`client_id` + `client_secret` não servem.** Numa conta de serviço quem assina é a
> chave privada; não existe versão com segredo curto. `client_id`/`client_secret` são
> credenciais de **OAuth**, que exigem alguém clicar em "Permitir" no navegador — e num
> servidor não há ninguém para fazer isso. (Dava para contornar guardando um
> `refresh_token`, mas ele expira em 7 dias enquanto o app estiver em modo *Testing*,
> e a campanha pararia sozinha no meio da semana.)

## 3. Aplicação

### Quantos domínios: **um só**

Não existe frontend separado. O FastAPI serve as telas e a API na mesma porta:

| Rota | O que é |
|---|---|
| `/` | tela de email |
| `/whatsapp` | tela de WhatsApp |
| `/api/*` | a API que as telas consomem |
| `/saude` | healthcheck |

O **Postgres não recebe domínio**. A aplicação fala com ele pela rede interna do Coolify,
via `DATABASE_URL`. Banco exposto na internet é risco sem contrapartida.

### Configurando

No Coolify: **+ New → Application → Public/Private Repository**.

- **Build Pack**: Dockerfile
- **Port Exposes**: `8010`
- **Health check path**: `/saude`
- **Domains**: um domínio, ex. `campanhas.shild.click`

Cole as variáveis de ambiente (seção 4). Deploy.

> Se preferir o `docker-compose.yaml` (**+ New → Docker Compose**), o Coolify mostra o
> serviço `campanhas` e um único campo de domínio para ele. O arquivo já traz
> `SERVICE_FQDN_CAMPANHAS_8010`, que é como o Coolify liga o domínio à porta 8010.

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
