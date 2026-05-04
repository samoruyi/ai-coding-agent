{{/*
Expand the name of the chart.
*/}}
{{- define "slack-gateway.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "slack-gateway.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "slack-gateway.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
app.kubernetes.io/name: {{ include "slack-gateway.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/component: gateway
app.kubernetes.io/part-of: coding-agent
{{- end -}}

{{- define "slack-gateway.selectorLabels" -}}
app.kubernetes.io/name: {{ include "slack-gateway.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "slack-gateway.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "slack-gateway.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{- define "slack-gateway.image" -}}
{{- $tag := .Values.image.tag | default .Chart.AppVersion -}}
{{- printf "%s:%s" .Values.image.repository $tag -}}
{{- end -}}

{{- define "slack-gateway.secretName" -}}
{{- if .Values.secrets.externalSecretName -}}
{{- .Values.secrets.externalSecretName -}}
{{- else -}}
{{- printf "%s-secrets" (include "slack-gateway.fullname" .) -}}
{{- end -}}
{{- end -}}
