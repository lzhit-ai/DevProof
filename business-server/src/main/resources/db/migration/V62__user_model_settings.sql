CREATE TABLE user_model_settings (
    user_id uuid PRIMARY KEY REFERENCES users(id),
    credential_id uuid NOT NULL UNIQUE,
    provider varchar(64) NOT NULL,
    model varchar(128) NOT NULL,
    base_url varchar(2048) NOT NULL,
    encrypted_api_key text NOT NULL,
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
