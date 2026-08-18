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

## 2. Aplicação

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

Cole as variáveis de ambiente (seção 3). Deploy.

> Se preferir o `docker-compose.yaml` (**+ New → Docker Compose**), o Coolify mostra o
> serviço `campanhas` e um único campo de domínio para ele. O arquivo já traz
> `SERVICE_FQDN_CAMPANHAS_8010`, que é como o Coolify liga o domínio à porta 8010.

## 3. Variáveis de ambiente

Obrigatórias:

| Variável | O que é |
|---|---|
| `DATABASE_URL` | Internal URL do Postgres criado no passo 1 |

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

Opcionais com padrão razoável: `TRANSPORTE` (`auto`), `MAIL_FROM_PER_EMPRESA` (`0`),
`SEND_DELAY_SECONDS` (`1.5`), `WA_DDD_PADRAO`, `EMAIL_LOGO_URL`, `SHILD_SITE_URL`,
`INSTAGRAM_URL`.

A lista completa e comentada está em [.env.example](.env.example).

## 4. Conferir se subiu certo

Abra `https://seu-dominio/saude`. Ele responde **200 mesmo com o banco fora** — é liveness,
não readiness — e o corpo diz o que está funcionando:

```json
{"ok": true, "banco_ok": true, "banco": "PostgreSQL 16...", "banco_alvo": "host:5432/postgres"}
```

Se `banco_ok` for `false`, o campo `banco_erro` diz o motivo e `banco_alvo` mostra qual host
foi tentado (sem a senha). Veja a seção 5.

Depois:

1. Abra a tela e importe a planilha de funcionários (passo 3)
2. Marque as empresas do disparo (passo 4)
3. Envie um teste por email e um por WhatsApp

---

## 5. Quando dá errado

### O container sobe e cai no mesmo instante

`/saude` não depende do banco, então isso é o **processo morrendo**. A causa mais comum
é variável de ambiente colada na anterior:

```
SEND_DELAY_SECONDS=1.5BREVO_API_KEY=xkeysib-...
                      ^^^^^^^^^^^^^^^^^^^^^^^^ virou parte do valor
```

Ao colar um bloco de variáveis no Coolify, confira se **cada uma ficou na sua própria
linha** — o editor às vezes junta a última com a primeira da colagem seguinte.

O sistema não morre mais por isso: valor numérico inválido cai no padrão e o problema
aparece em `/saude` (campo `config_problemas`) e no topo da tela. Se `PORT` for o afetado,
porém, a porta muda e o healthcheck falha — aí o container cai mesmo.

Se as variáveis estiverem certas, veja os logs do container no Coolify.

> `/saude/pronto` existe e devolve 503 enquanto o banco não responde. **Não** use ele como
> healthcheck: o container passaria a reiniciar em loop justo quando você precisa abrir a
> tela para diagnosticar.

### `banco_ok: false` — a aplicação não enxerga o Postgres

O sintoma é o `DATABASE_URL` apontar para um host interno do Coolify
(`postgres://...@yyz1i7qozmdlgh35ldphrltt:5432/postgres`) que a aplicação não resolve.

Um banco criado no Coolify fica na rede `coolify`; uma aplicação, por padrão, fica numa
rede própria. Elas não se enxergam até você ligar:

**Aplicação → Configuration → Network → "Connect To Predefined Network" = ON** → redeploy.

Confira depois em `/saude`: `banco_ok` deve virar `true`.

Alternativa pior: expor o Postgres publicamente e usar a URL externa. Evite.

---

## Rodar na sua máquina

Continua funcionando sem Docker e sem Postgres: com `DATABASE_URL` vazio o sistema usa
um SQLite local em `saidas/campanhas.db`.

```powershell
cd "C:\Users\Matheus Fontenele\Documents\projetos\SHILD\shild-system\RSPV capaign"
.\venv\Scripts\python.exe run.py
```

## Segurança

O sistema **não tem login**. Quem abrir a URL dispara campanha e vê os dados dos funcionários.
Não exponha num domínio público sem proteção — no Coolify, ative autenticação básica
no proxy, ou deixe acessível só por rede interna/VPN.
