-- =============================================================================
-- ESTRUTURA DE TABELAS — CACHE OCTADESK NO BANCO OCTADESK
-- =============================================================================
-- Solicitar ao time de infra: criar as 3 tabelas abaixo no banco `octadesk`
-- com o usuário de escrita (DB_WRITE_USER).
--
-- Dependências: nenhuma (tabelas independentes de `chat_ai_evaluations`).
-- Engine: InnoDB | Charset: utf8mb4_unicode_ci
-- =============================================================================


-- -----------------------------------------------------------------------------
-- 1. chats
--    Espelha os dados brutos de cada conversa retornada pela API do Octadesk.
--    Campos extraídos do raw_json para facilitar consultas analíticas.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS octadesk.chats (
    id                  VARCHAR(100)    NOT NULL            COMMENT 'ID único do chat na Octadesk',
    status              VARCHAR(50)                         COMMENT 'Status do chat (opened, closed, etc.)',
    created_at          DATETIME                            COMMENT 'Data de criação do chat (UTC convertido)',
    updated_at_octa     DATETIME                            COMMENT 'Última atualização na Octadesk (UTC)',
    closed_at           DATETIME                            COMMENT 'Data de fechamento do chat',
    phone               VARCHAR(100)                        COMMENT 'Telefone(s) do contato (ex: +5521967261242)',
    contact_name        VARCHAR(255)                        COMMENT 'Nome do contato/lead',
    agent_name          VARCHAR(255)                        COMMENT 'Nome do agente/vendedor responsável',
    channel             VARCHAR(100)                        COMMENT 'Canal de origem (whatsapp, email, etc.)',
    tags                TEXT                                COMMENT 'Tags do chat em formato JSON array string',
    `group`             VARCHAR(255)                        COMMENT 'Grupo/fila do atendimento',
    origin              VARCHAR(100)                        COMMENT 'Origem do contato',
    bot_name            VARCHAR(255)                        COMMENT 'Nome do bot que fez a triagem inicial',
    survey_response     TEXT                                COMMENT 'Resposta da pesquisa de satisfação (NPS)',
    raw_json            LONGTEXT                            COMMENT 'Payload completo retornado pela API (JSON)',
    cached_at           DATETIME        NOT NULL            COMMENT 'Quando foi inserido no cache SQLite local',
    synced_at           DATETIME        NOT NULL
                        DEFAULT CURRENT_TIMESTAMP
                        ON UPDATE CURRENT_TIMESTAMP         COMMENT 'Última sincronização com este banco MySQL',

    PRIMARY KEY (id),
    INDEX idx_status        (status),
    INDEX idx_created_at    (created_at),
    INDEX idx_phone         (phone),
    INDEX idx_agent         (agent_name),
    INDEX idx_channel       (channel)
)
ENGINE = InnoDB
DEFAULT CHARSET = utf8mb4
COLLATE = utf8mb4_unicode_ci
COMMENT = 'Chats Octadesk — espelho do cache SQLite local';


-- -----------------------------------------------------------------------------
-- 2. messages
--    Mensagens individuais de cada chat. FK para chats.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS octadesk.messages (
    id          VARCHAR(200)    NOT NULL            COMMENT 'ID único da mensagem (id da API ou chat_id_idx)',
    chat_id     VARCHAR(100)    NOT NULL            COMMENT 'ID do chat pai (FK → chats.id)',
    raw_json    LONGTEXT                            COMMENT 'Payload completo da mensagem (JSON)',
    cached_at   DATETIME        NOT NULL            COMMENT 'Quando foi inserido no cache SQLite local',
    synced_at   DATETIME        NOT NULL
                DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP         COMMENT 'Última sincronização com este banco MySQL',

    PRIMARY KEY (id),
    INDEX idx_chat_id   (chat_id),
    CONSTRAINT fk_messages_chat
        FOREIGN KEY (chat_id)
        REFERENCES octadesk.chats (id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
)
ENGINE = InnoDB
DEFAULT CHARSET = utf8mb4
COLLATE = utf8mb4_unicode_ci
COMMENT = 'Mensagens dos chats — espelho do cache SQLite local';


-- -----------------------------------------------------------------------------
-- 3. sync_log
--    Histórico de cada execução de sincronização (cron ou manual).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS octadesk.sync_log (
    id                  INT             NOT NULL AUTO_INCREMENT,
    sync_type           VARCHAR(50)                         COMMENT 'Tipo: cron | manual | migration',
    source              VARCHAR(50)     DEFAULT 'sqlite'    COMMENT 'Origem: sqlite | api',
    pages_fetched       INT                                 COMMENT 'Páginas buscadas na API nesta execução',
    chats_saved         INT             DEFAULT 0           COMMENT 'Chats inseridos/atualizados nesta execução',
    messages_saved      INT             DEFAULT 0           COMMENT 'Mensagens inseridas/atualizadas nesta execução',
    oldest_chat_date    VARCHAR(50)                         COMMENT 'Data mais antiga dos chats processados',
    newest_chat_date    VARCHAR(50)                         COMMENT 'Data mais recente dos chats processados',
    duration_seconds    DECIMAL(10,2)                       COMMENT 'Duração da execução em segundos',
    error_message       TEXT                                COMMENT 'Mensagem de erro, se houver',
    synced_at           DATETIME        NOT NULL
                        DEFAULT CURRENT_TIMESTAMP           COMMENT 'Timestamp de início da sincronização',

    PRIMARY KEY (id),
    INDEX idx_sync_type (sync_type),
    INDEX idx_synced_at (synced_at)
)
ENGINE = InnoDB
DEFAULT CHARSET = utf8mb4
COLLATE = utf8mb4_unicode_ci
COMMENT = 'Log de sincronizações do cache Octadesk';
