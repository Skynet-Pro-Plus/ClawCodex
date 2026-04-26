//! Interactive OpenRouter model list for portable installs (mirrors launch.ps1).

use std::io::{self, IsTerminal, Write};

use api::{read_openai_api_key, read_openai_compat_base_url, OpenAiCompatConfig};
use serde::Deserialize;
use serde_json::Value;

/// Default model id when the user presses Enter (matches `launch.ps1`).
pub const OPENROUTER_DEFAULT_MODEL_ID: &str = "openai/gpt-4.1-mini";

const OPENROUTER_MODELS_URL: &str = "https://openrouter.ai/api/v1/models";
const MIN_CLAW_CONTEXT_TOKENS: u32 = 128_000;

#[derive(Debug, Clone)]
pub struct OpenRouterModelRow {
    pub id: String,
    pub provider_display: String,
    pub name: String,
    pub context_length: Option<u32>,
    pub modality: Option<String>,
    pub prompt_price_per_million: Option<String>,
    pub completion_price_per_million: Option<String>,
}

#[derive(Deserialize)]
struct ModelsEnvelope {
    data: Vec<Value>,
}

/// Whether the REPL should offer the OpenRouter model picker before connecting.
#[must_use]
pub fn should_run_openrouter_repl_model_picker(model_explicit: bool) -> bool {
    if model_explicit {
        return false;
    }
    if std::env::var("CLAW_SKIP_OPENROUTER_MODEL_PICKER")
        .ok()
        .as_deref()
        == Some("1")
    {
        return false;
    }
    if !io::stdin().is_terminal() || !io::stdout().is_terminal() {
        return false;
    }
    if !api::has_api_key("OPENAI_API_KEY") {
        return false;
    }
    let base = read_openai_compat_base_url(OpenAiCompatConfig::openai());
    base.contains("openrouter")
}

fn provider_title_case(provider_id: &str) -> String {
    provider_id
        .split('-')
        .map(|word| {
            let mut chars = word.chars();
            match chars.next() {
                None => String::new(),
                Some(first) => first.to_uppercase().collect::<String>() + chars.as_str(),
            }
        })
        .collect::<Vec<_>>()
        .join(" ")
}

fn provider_display_name(provider_id: &str) -> String {
    match provider_id {
        "ai21" => "AI21".to_string(),
        "aion-labs" => "Aion Labs".to_string(),
        "alfredpros" => "AlfredPros".to_string(),
        "allenai" => "AllenAI".to_string(),
        "anthracite-org" => "Anthracite Org".to_string(),
        "arcee-ai" => "Arcee AI".to_string(),
        "bytedance-seed" => "ByteDance Seed".to_string(),
        "deepseek" => "DeepSeek".to_string(),
        "essentialai" => "EssentialAI".to_string(),
        "ibm-granite" => "IBM Granite".to_string(),
        "kwaipilot" => "KwaiPilot".to_string(),
        "meta-llama" => "Meta Llama".to_string(),
        "minimax" => "MiniMax".to_string(),
        "mistralai" => "MistralAI".to_string(),
        "moonshotai" => "MoonshotAI".to_string(),
        "nousresearch" => "NousResearch".to_string(),
        "nvidia" => "NVIDIA".to_string(),
        "openai" => "OpenAI".to_string(),
        "openrouter" => "OpenRouter".to_string(),
        "perplexity" => "Perplexity".to_string(),
        "prime-intellect" => "Prime Intellect".to_string(),
        "qwen" => "Qwen".to_string(),
        "rekaai" => "RekaAI".to_string(),
        "thedrummer" => "TheDrummer".to_string(),
        "tngtech" => "TNGTech".to_string(),
        "upstage" => "Upstage".to_string(),
        "x-ai" => "xAI".to_string(),
        "z-ai" => "Z.AI".to_string(),
        other => provider_title_case(other),
    }
}

fn openrouter_model_passes_claw_filters(raw: &Value) -> bool {
    let supported: Vec<&str> = raw
        .get("supported_parameters")
        .and_then(Value::as_array)
        .map(|items| items.iter().filter_map(Value::as_str).collect::<Vec<_>>())
        .unwrap_or_default();
    if supported.is_empty()
        || !supported.iter().any(|p| *p == "max_tokens")
        || !supported.iter().any(|p| *p == "tools")
    {
        return false;
    }

    if let Some(out_mods) = raw
        .pointer("/architecture/output_modalities")
        .and_then(Value::as_array)
    {
        if !out_mods.is_empty() && !out_mods.iter().any(|v| v.as_str() == Some("text")) {
            return false;
        }
    }

    let modality = raw
        .pointer("/architecture/modality")
        .and_then(Value::as_str)
        .unwrap_or("");
    if modality.is_empty() {
        return model_has_claw_sized_context(raw);
    }
    modality.contains("->text") && model_has_claw_sized_context(raw)
}

fn model_has_claw_sized_context(raw: &Value) -> bool {
    raw.get("context_length")
        .and_then(Value::as_u64)
        .and_then(|n| u32::try_from(n).ok())
        .is_some_and(|n| n >= MIN_CLAW_CONTEXT_TOKENS)
}

fn format_price_per_million(raw: Option<&Value>) -> Option<String> {
    let price = raw.and_then(|v| match v {
        Value::String(s) => s.parse::<f64>().ok(),
        Value::Number(n) => n.as_f64(),
        _ => None,
    })?;
    if !price.is_finite() || price < 0.0 {
        return None;
    }
    let per_million = price * 1_000_000.0;
    if per_million <= f64::EPSILON {
        Some("$0/M".to_string())
    } else if per_million < 0.01 {
        Some(format!("${per_million:.4}/M"))
    } else if per_million < 1.0 {
        Some(format!("${per_million:.3}/M"))
    } else {
        Some(format!("${per_million:.2}/M"))
    }
}

fn parse_model_row(raw: &Value) -> Option<OpenRouterModelRow> {
    let id_str = raw.get("id")?.as_str()?;
    if id_str.trim().is_empty() || !id_str.contains('/') {
        return None;
    }
    if !openrouter_model_passes_claw_filters(raw) {
        return None;
    }
    let (provider_id, slug) = id_str.split_once('/')?;
    let id = id_str.to_string();
    let name = raw
        .get("name")
        .and_then(Value::as_str)
        .unwrap_or(slug)
        .to_string();
    let context_length = raw
        .get("context_length")
        .and_then(|v| v.as_u64())
        .and_then(|n| u32::try_from(n).ok());
    let modality = raw
        .pointer("/architecture/modality")
        .and_then(Value::as_str)
        .map(str::to_string);
    let prompt_price_per_million = format_price_per_million(raw.pointer("/pricing/prompt"));
    let completion_price_per_million = format_price_per_million(raw.pointer("/pricing/completion"));

    Some(OpenRouterModelRow {
        id,
        provider_display: provider_display_name(provider_id),
        name,
        context_length,
        modality,
        prompt_price_per_million,
        completion_price_per_million,
    })
}

fn fetch_openrouter_models(api_key: &str) -> Result<Vec<OpenRouterModelRow>, String> {
    let client = reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(120))
        .build()
        .map_err(|e| format!("HTTP client: {e}"))?;

    let response = client
        .get(OPENROUTER_MODELS_URL)
        .header(reqwest::header::AUTHORIZATION, format!("Bearer {api_key}"))
        .send()
        .map_err(|e| format!("OpenRouter models request failed: {e}"))?;

    if !response.status().is_success() {
        return Err(format!(
            "OpenRouter models HTTP {}: {}",
            response.status().as_u16(),
            response.text().unwrap_or_default()
        ));
    }

    let envelope: ModelsEnvelope = response
        .json()
        .map_err(|e| format!("OpenRouter models JSON: {e}"))?;

    let mut rows: Vec<OpenRouterModelRow> = envelope
        .data
        .iter()
        .filter_map(|raw| parse_model_row(raw))
        .collect();

    rows.sort_by(|a, b| {
        a.provider_display
            .cmp(&b.provider_display)
            .then_with(|| a.name.cmp(&b.name))
            .then_with(|| a.id.cmp(&b.id))
    });

    Ok(rows)
}

/// Returns `(model_id, optional_context_window)` after interactive selection.
pub fn run_openrouter_model_picker() -> Result<(String, Option<u32>), String> {
    let Some(api_key) = read_openai_api_key() else {
        return Err("OPENAI_API_KEY is not set.".to_string());
    };

    eprintln!("Fetching models from OpenRouter (timeout 120s)...");
    let models = fetch_openrouter_models(&api_key)?;
    if models.is_empty() {
        return Err("OpenRouter returned no models matching Claw filters.".to_string());
    }

    eprintln!();
    eprintln!(
        "OpenRouter models (tool use + text output + >= {MIN_CLAW_CONTEXT_TOKENS} context) - alphabetical by provider."
    );
    eprintln!("Prices are input/output per 1M tokens when OpenRouter reports pricing.");
    eprintln!("Press Enter for the default, type a number to choose, or paste an exact model id.");
    eprintln!();

    let mut display_index = 1usize;
    let mut last_provider: Option<String> = None;
    for model in &models {
        if last_provider.as_deref() != Some(model.provider_display.as_str()) {
            if last_provider.is_some() {
                eprintln!();
            }
            eprintln!("{}", model.provider_display);
            last_provider = Some(model.provider_display.clone());
        }
        let ctx = model
            .context_length
            .map(|n| format!(" | ctx {n}"))
            .unwrap_or_default();
        let modality = model
            .modality
            .as_deref()
            .map(|m| format!(" | {m}"))
            .unwrap_or_default();
        let pricing = match (
            model.prompt_price_per_million.as_deref(),
            model.completion_price_per_million.as_deref(),
        ) {
            (Some(prompt), Some(completion)) => format!(" | in {prompt} out {completion}"),
            (Some(prompt), None) => format!(" | in {prompt} out ?"),
            (None, Some(completion)) => format!(" | in ? out {completion}"),
            (None, None) => String::new(),
        };
        eprintln!(
            "  [{display_index}] {} ({}{ctx}{pricing}{modality})",
            model.id, model.name
        );
        display_index += 1;
    }
    eprintln!();

    let stdin = io::stdin();
    loop {
        print!("Model selection [{OPENROUTER_DEFAULT_MODEL_ID}]: ");
        let _ = io::stdout().flush();
        let mut line = String::new();
        stdin
            .read_line(&mut line)
            .map_err(|e| format!("stdin: {e}"))?;
        let selection = line.trim();

        if selection.is_empty() {
            let default_row = models.iter().find(|m| m.id == OPENROUTER_DEFAULT_MODEL_ID);
            return Ok((
                OPENROUTER_DEFAULT_MODEL_ID.to_string(),
                default_row.and_then(|m| m.context_length),
            ));
        }

        if let Ok(n) = selection.parse::<usize>() {
            if n >= 1 && n <= models.len() {
                let picked = &models[n - 1];
                return Ok((picked.id.clone(), picked.context_length));
            }
            eprintln!("Selection '{selection}' is out of range.");
            continue;
        }

        if let Some(picked) = models.iter().find(|m| m.id == selection) {
            return Ok((picked.id.clone(), picked.context_length));
        }

        eprintln!("Model '{selection}' was not in the fetched OpenRouter list.");
    }
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::{format_price_per_million, openrouter_model_passes_claw_filters, parse_model_row};

    fn compatible_model() -> serde_json::Value {
        json!({
            "id": "openai/gpt-4.1-mini",
            "name": "GPT 4.1 Mini",
            "context_length": 1_000_000,
            "supported_parameters": ["tools", "max_tokens", "temperature"],
            "architecture": {
                "modality": "text->text",
                "output_modalities": ["text"]
            },
            "pricing": {
                "prompt": "0.00000015",
                "completion": "0.00000060"
            }
        })
    }

    #[test]
    fn filters_for_tool_text_and_large_context_models() {
        assert!(openrouter_model_passes_claw_filters(&compatible_model()));

        let mut no_tools = compatible_model();
        no_tools["supported_parameters"] = json!(["max_tokens"]);
        assert!(!openrouter_model_passes_claw_filters(&no_tools));

        let mut small_context = compatible_model();
        small_context["context_length"] = json!(32_000);
        assert!(!openrouter_model_passes_claw_filters(&small_context));

        let mut image_only = compatible_model();
        image_only["architecture"]["output_modalities"] = json!(["image"]);
        assert!(!openrouter_model_passes_claw_filters(&image_only));
    }

    #[test]
    fn parses_context_and_token_pricing_for_display() {
        let row = parse_model_row(&compatible_model()).expect("compatible row");
        assert_eq!(row.context_length, Some(1_000_000));
        assert_eq!(row.prompt_price_per_million.as_deref(), Some("$0.150/M"));
        assert_eq!(
            row.completion_price_per_million.as_deref(),
            Some("$0.600/M")
        );
    }

    #[test]
    fn formats_openrouter_per_token_price_as_per_million() {
        assert_eq!(
            format_price_per_million(Some(&json!("0.000002"))).as_deref(),
            Some("$2.00/M")
        );
        assert_eq!(
            format_price_per_million(Some(&json!(0))).as_deref(),
            Some("$0/M")
        );
        assert!(format_price_per_million(Some(&json!("not-a-number"))).is_none());
    }
}
