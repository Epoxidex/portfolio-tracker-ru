#!/bin/sh
set -eu

secret_file=${PORTFOLIO_GITHUB_TOKEN_FILE:-/run/secrets/github_backup_token}
prompt=${1:-}

case "$prompt" in
    *github.com*)
        case "$prompt" in
            *Username*|*username*)
                printf '%s\n' 'x-access-token'
                ;;
            *Password*|*password*)
                if [ ! -r "$secret_file" ] || [ ! -s "$secret_file" ]; then
                    printf '%s\n' 'GitHub token secret is missing or empty' >&2
                    exit 1
                fi
                sed -n '1p' "$secret_file"
                ;;
            *)
                printf '%s\n' 'Unexpected GitHub credential prompt' >&2
                exit 1
                ;;
        esac
        ;;
    *)
        printf '%s\n' 'Refusing to provide GitHub credentials to another host' >&2
        exit 1
        ;;
esac
