FROM python:3.12.10-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app/agent-service
RUN apt-get update && apt-get install --no-install-recommends -y git openssh-client \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 devproof \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin devproof \
    && mkdir -p /repository-cache && chown 10001:10001 /repository-cache
COPY agent-service/pyproject.toml agent-service/uv.lock ./
RUN python -c "import tomllib; data=tomllib.load(open('uv.lock','rb')); open('/tmp/requirements.txt','w').write('\n'.join(p['name']+'=='+p['version']+' '+ ' '.join('--hash='+a['hash'] for a in ([p['sdist']] if 'sdist' in p else [])+p.get('wheels',[])) for p in data['package'] if 'registry' in p.get('source',{})))" \
    && pip install --no-cache-dir --require-hashes -r /tmp/requirements.txt
RUN python -c "import tree_sitter_language_pack as p; p.configure(p.PackConfig(cache_dir='/parser-cache')); p.download(['java','python','javascript','typescript','tsx']); [p.get_parser(x) for x in ['java','python','javascript','typescript','tsx']]" \
    && chown -R 10001:10001 /parser-cache
COPY agent-service/src ./src
COPY contracts/schemas /app/contracts/schemas
RUN pip install --no-cache-dir --no-deps .
USER 10001:10001
ENV CONTRACT_SCHEMA_ROOT=/app/contracts/schemas TREE_SITTER_CACHE_ROOT=/parser-cache
CMD ["python", "-m", "devproof_agent.service"]
