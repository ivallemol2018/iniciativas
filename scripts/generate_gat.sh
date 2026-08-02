#!/bin/bash

set -o pipefail

# Variables necesarias
client_id=$APP_ID
PRIVATE_KEY=$PRIVATE_KEY
ORGANIZATION=$ORGANIZATION

# Imprimir el APP_ID para depuracion
echo "APP_ID: $client_id"

# Verificar si la clave privada esta presente
if [ -z "$PRIVATE_KEY" ]; then
	echo "Private key is missing."
	exit 1
fi

#Generar JWT
now=$(date +%s)
iat=$((${now} - 60)) 
exp=$((${now} + 600))

b64enc() { openssl base64 -e -A | tr -d '=' | tr '/+' '_-' | tr -d '\n'; }

header_json='{
	"typ": "JWT",
	"alg": "RS256"
}'

header=$(echo -n "${header_json}" | b64enc)

payload_json="{
	\"iat\":${iat},
	\"exp\":${exp},
	\"iss\":\"${client_id}\"
}"

payload=$(echo -n "${payload_json}" | b64enc)


header_payload="${header}.${payload}"
signature=$(echo -n "${header_payload}" | openssl dgst -sha256 -sign <echo -n "${PRIVATE_KEY}" | b64enc)


jwt_token="${header_payload}.${signature}"


installations=$(curl -s -H "Authorization: Bearer $jwt_token" -H "Accept: application/vnd.github.v3+json" https://api.github.com/app/installations)


installation_id=$(echo "$installations" | jq -r --arg org "$ORGANIZATION" '.[] | select(.account.login == $org) | .id')

if [ -z "$installation_id" ]; then
	echo "No matching account found for the provided organization."
	exit 1
fi

echo "ID de installation seleccionado_: $installation_id"

access_token=$(curl -s -X POST -H "Authorization: Bearer $jwt_token" -H "Accept: application/vnd.github.v3+json" https://api.github.com/app/installations/$installation_id/access_tokens | jq -r '.token' )

if [ -z "$access_token" ]; then
	echo "Failed to obtain access token"
	exit 1
fi


echo "ACCESS_TOKEN=$access_token" >> $GITHUB_ENV


if [ -n "$1" ]; then
	output_name="$1"
	echo "$output_name=$access_token" >> "$GITHUB_OUTPUT"
fi






