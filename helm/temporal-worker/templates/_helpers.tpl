{{- define "temporal-worker.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "temporal-worker.fullname" -}}
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

{{- define "temporal-worker.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
app.kubernetes.io/name: {{ include "temporal-worker.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/component: worker
app.kubernetes.io/part-of: coding-agent
{{- end -}}

{{- define "temporal-worker.selectorLabels" -}}
app.kubernetes.io/name: {{ include "temporal-worker.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "temporal-worker.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "temporal-worker.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{- define "temporal-worker.image" -}}
{{- $tag := .Values.image.tag | default .Chart.AppVersion -}}
{{- printf "%s:%s" .Values.image.repository $tag -}}
{{- end -}}

{{- define "temporal-worker.secretName" -}}
{{- if .Values.secrets.externalSecretName -}}
{{- .Values.secrets.externalSecretName -}}
{{- else -}}
{{- printf "%s-secrets" (include "temporal-worker.fullname" .) -}}
{{- end -}}
{{- end -}}
