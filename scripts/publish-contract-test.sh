#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
bash -n \
  "${repo_root}/scripts/publish-image.sh" \
  "${repo_root}/scripts/publish-mod-from-image.sh"

test_dir="$(mktemp -d)"
cleanup() {
  rm -rf "${test_dir}"
}
trap cleanup EXIT

export FAKE_DOCKER_LOG="${test_dir}/docker.log"

docker() {
  local command="${1:-}"
  shift || true

  printf '%s' "${command}" >>"${FAKE_DOCKER_LOG}"
  for argument in "$@"; do
    printf '\t%s' "${argument}" >>"${FAKE_DOCKER_LOG}"
  done
  printf '\n' >>"${FAKE_DOCKER_LOG}"

  case "${command}" in
    login)
      cat >/dev/null
      ;;
    create)
      case " $* " in
        *" ward exec publish-mod-packages "*)
          printf 'publisher-container\n'
          ;;
        *)
          printf 'image-container\n'
          ;;
      esac
      ;;
    wait)
      printf '%s\n' "${FAKE_PUBLISHER_STATUS:-0}"
      ;;
    cp | pull | rm | start)
      ;;
    *)
      printf 'unexpected docker command in publisher contract test: %s\n' "${command}" >&2
      return 1
      ;;
  esac
}
export -f docker

(
  cd "${repo_root}"
  REGISTRY_TOKEN="test-registry-token" \
    FORGEJO_PACKAGE_TOKEN="test-package-token" \
    MOD_PACKAGE_NAME="eco-replay" \
    GITHUB_SHA="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" \
    GITHUB_SERVER_URL="https://forgejo.invalid" \
    FORGEJO_EGRESS_PROXY="http://proxy.invalid" \
    bash scripts/publish-mod-from-image.sh
)

require_log_entry() {
  local expected="$1"
  if ! rg --fixed-strings --quiet -- "${expected}" "${FAKE_DOCKER_LOG}"; then
    printf 'publisher contract is missing docker operation: %s\n' "${expected}" >&2
    return 1
  fi
}

expected_repo_copy="$(
  printf 'cp\t%s\t%s' \
    "${repo_root}/." \
    "publisher-container:/workspace/"
)"
require_log_entry $'create\t--workdir\t/workspace'
require_log_entry $'\tward\texec\tpublish-mod-packages'
require_log_entry "${expected_repo_copy}"
require_log_entry "publisher-container:/packages"
require_log_entry $'start\t--attach\tpublisher-container'
require_log_entry $'wait\tpublisher-container'

if rg --fixed-strings --quiet -- "--volume" "${FAKE_DOCKER_LOG}"; then
  printf 'publisher contract must not bind-mount runner-local paths\n' >&2
  exit 1
fi

set +e
(
  cd "${repo_root}"
  REGISTRY_TOKEN="test-registry-token" \
    FORGEJO_PACKAGE_TOKEN="test-package-token" \
    MOD_PACKAGE_NAME="eco-replay" \
    GITHUB_SHA="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" \
    GITHUB_SERVER_URL="https://forgejo.invalid" \
    FORGEJO_EGRESS_PROXY="http://proxy.invalid" \
    FAKE_PUBLISHER_STATUS="17" \
    bash scripts/publish-mod-from-image.sh >/dev/null 2>&1
)
publisher_failure_status=$?
set -e
if [ "${publisher_failure_status}" -ne 17 ]; then
  printf 'publisher container failure returned status %s, expected 17\n' \
    "${publisher_failure_status}" >&2
  exit 1
fi

printf 'publisher repository-context contract passed\n'
