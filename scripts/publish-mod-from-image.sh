#!/usr/bin/env bash
set -euo pipefail

registry="forgejo.coilysiren.me"
image_name="coilyco-gaming/eco-app"
dev_image="${registry}/coilyco-flight-deck/agentic-os:release"

for required in REGISTRY_TOKEN FORGEJO_PACKAGE_TOKEN MOD_PACKAGE_NAME; do
  if [ -z "${!required:-}" ]; then
    echo "${required} is required for the trusted mod-package lane." >&2
    exit 1
  fi
done

sha="${GITHUB_SHA:-$(git rev-parse HEAD)}"
case "${sha}" in
  *[!0-9a-f]*|"")
    echo "eco-app source sha is not a lowercase hexadecimal commit id." >&2
    exit 1
    ;;
esac
if [ "${#sha}" -ne 40 ]; then
  echo "eco-app source sha must be a full 40-character commit id." >&2
  exit 1
fi

image="${registry}/${image_name}:${sha}"
docker_config="$(mktemp -d)"
package_dir="$(mktemp -d)"
container_id=""
cleanup() {
  if [ -n "${container_id}" ]; then
    docker rm -f "${container_id}" >/dev/null 2>&1 || true
  fi
  rm -rf "${docker_config}" "${package_dir}"
}
trap cleanup EXIT
chmod 700 "${docker_config}" "${package_dir}"
export DOCKER_CONFIG="${docker_config}"

printf '%s' "${REGISTRY_TOKEN}" \
  | docker login "${registry}" --username coilyco-ops --password-stdin
docker pull "${image}"

container_id="$(docker create "${image}")"
docker cp "${container_id}:/mod-packages/." "${package_dir}/"
docker rm -f "${container_id}" >/dev/null
container_id=""

export FORGEJO_PACKAGE_URL="${GITHUB_SERVER_URL:-https://forgejo.coilysiren.me}"
export FORGEJO_PACKAGE_OWNER="coilyco-gaming"
export FORGEJO_PACKAGE_USER="coilyco-ops"
export MOD_PACKAGE_DIR="/packages"
export HTTP_PROXY="${FORGEJO_EGRESS_PROXY:-}"
export HTTPS_PROXY="${FORGEJO_EGRESS_PROXY:-}"

repo_root="$(pwd -P)"
docker run --rm \
  --volume "${repo_root}:/workspace" \
  --volume "${package_dir}:/packages:ro" \
  --workdir /workspace \
  --env FORGEJO_PACKAGE_URL \
  --env FORGEJO_PACKAGE_OWNER \
  --env FORGEJO_PACKAGE_USER \
  --env FORGEJO_PACKAGE_TOKEN \
  --env MOD_PACKAGE_DIR \
  --env MOD_PACKAGE_NAME \
  --env HTTP_PROXY \
  --env HTTPS_PROXY \
  "${dev_image}" \
  ward exec publish-mod-packages
