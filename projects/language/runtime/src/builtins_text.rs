use crate::error::RuntimeError;
use crate::value::Value;

pub(crate) fn runtime_int(value: &Value) -> Result<i64, RuntimeError> {
    match value {
        Value::Int(n) => Ok(*n),
        other => Err(RuntimeError::InvalidOperand(format!("forventet heltall, fikk {other:?}"))),
    }
}

pub(crate) fn is_word_char(text: &str) -> bool {
    let mut chars = text.chars();
    let Some(ch) = chars.next() else {
        return false;
    };
    if chars.next().is_some() {
        return false;
    }
    matches!(
        ch,
        '_' | 'a'..='z' | 'A'..='Z' | '0'..='9' | 'æ' | 'ø' | 'å' | 'Æ' | 'Ø' | 'Å'
    )
}

pub(crate) fn sass_replace_variables(text: &str, variables: &std::collections::BTreeMap<String, String>) -> String {
    let mut result = text.to_string();
    for (name, value) in variables {
        result = result.replace(&format!("${name}"), value);
    }
    result
}

pub(crate) fn sass_to_css(source: &str) -> String {
    let mut variables: std::collections::BTreeMap<String, String> = std::collections::BTreeMap::new();
    let mut selector_stack: Vec<String> = Vec::new();
    let mut output: Vec<String> = Vec::new();

    for raw_line in source.lines() {
        let mut line = raw_line.trim().to_string();
        if line.is_empty() || line.starts_with("//") || line.starts_with("/*") || line.starts_with('*') {
            continue;
        }

        if line.starts_with('$') && line.contains(':') && line.ends_with(';') {
            let mut parts = line[1..].splitn(2, ':');
            let name = parts.next().unwrap_or("").trim().to_string();
            let value = parts.next().unwrap_or("").trim().trim_end_matches(';').to_string();
            variables.insert(name, sass_replace_variables(&value, &variables));
            continue;
        }

        line = sass_replace_variables(&line, &variables);

        if line.ends_with('{') {
            let mut selector = line.trim_end_matches('{').trim().to_string();
            if selector.starts_with('&') && !selector_stack.is_empty() {
                selector = selector.replacen('&', selector_stack.last().unwrap(), 1);
            } else if let Some(parent) = selector_stack.last() {
                selector = format!("{parent} {selector}");
            }
            selector_stack.push(selector);
            continue;
        }

        if line == "}" {
            let _ = selector_stack.pop();
            continue;
        }

        if line.contains(':') && line.ends_with(';') {
            let current_selector = selector_stack.last().cloned().unwrap_or_default();
            if !current_selector.is_empty() {
                output.push(format!("{current_selector} {{ {line} }}"));
            } else {
                output.push(line);
            }
            continue;
        }
    }

    if output.is_empty() {
        String::new()
    } else {
        format!("{}\n", output.join("\n"))
    }
}

pub(crate) fn tokenize_expression(text: &str) -> Vec<String> {
    let chars: Vec<char> = text.chars().collect();
    let mut tokens = Vec::new();
    let mut i = 0;
    while i < chars.len() {
        let rest: String = chars[i..].iter().collect();
        let matched = [
            "<=>", "<->", "=>", "->", "<-", "&&", "||", "+=", "-=", "*=", "/=", "%=", "==", "!=",
            "<=", ">=", "<>", "=", "!", "(", ")", "{", "}", "[", "]", ",", ".", ":", ";", "+",
            "-", "*", "/", "%", "<", ">",
        ]
        .iter()
        .find(|token| rest.starts_with(**token))
        .map(|token| token.to_string());
        if let Some(token) = matched {
            tokens.push(token.clone());
            i += token.chars().count();
            continue;
        }
        if chars[i] == '"' {
            let mut j = i + 1;
            let mut escaped = false;
            while j < chars.len() {
                let ch = chars[j];
                if escaped {
                    escaped = false;
                } else if ch == '\\' {
                    escaped = true;
                } else if ch == '"' {
                    j += 1;
                    break;
                }
                j += 1;
            }
            tokens.push(chars[i..j.min(chars.len())].iter().collect());
            i = j.min(chars.len());
            continue;
        }
        if chars[i].is_alphabetic()
            || chars[i] == '_'
            || matches!(chars[i], 'æ' | 'ø' | 'å' | 'Æ' | 'Ø' | 'Å')
        {
            let mut j = i + 1;
            while j < chars.len()
                && (chars[j].is_alphanumeric()
                    || chars[j] == '_'
                    || matches!(chars[j], 'æ' | 'ø' | 'å' | 'Æ' | 'Ø' | 'Å'))
            {
                j += 1;
            }
            tokens.push(chars[i..j].iter().collect());
            i = j;
            continue;
        }
        if chars[i].is_ascii_digit() {
            let mut j = i + 1;
            while j < chars.len() && chars[j].is_ascii_digit() {
                j += 1;
            }
            tokens.push(chars[i..j].iter().collect());
            i = j;
            continue;
        }
        if !chars[i].is_whitespace() {
            tokens.push(chars[i].to_string());
        }
        i += 1;
    }
    tokens
}

pub(crate) fn handle_text_builtin(name: &str, args: &[Value]) -> Result<Option<Value>, RuntimeError> {
    match name {
        "lengde" => {
            let value = args.first().cloned().unwrap_or_else(|| Value::list(Vec::new()));
            Ok(Some(Value::Int(match value {
                Value::List(items) => items.borrow().len() as i64,
                Value::Text(text) => text.chars().count() as i64,
                _ => 0,
            })))
        }
        "tekst_fra_heltall" => {
            let value = args.first().map(format_value).unwrap_or_default();
            Ok(Some(Value::Text(value)))
        }
        "tekst_fra_bool" => {
            let value = args.first().map(|v| v.is_truthy()).unwrap_or(false);
            Ok(Some(Value::Text(if value { "sann" } else { "usann" }.to_string())))
        }
        "tekst_til_små" => {
            let text = args.first().map(format_value).unwrap_or_default();
            Ok(Some(Value::Text(text.to_lowercase())))
        }
        "tekst_til_store" => {
            let text = args.first().map(format_value).unwrap_or_default();
            Ok(Some(Value::Text(text.to_uppercase())))
        }
        "tekst_til_tittel" => {
            let text = args.first().map(format_value).unwrap_or_default();
            let mut out = String::new();
            let mut new_word = true;
            for ch in text.chars() {
                if ch.is_alphanumeric() || ch == '_' || matches!(ch, 'æ' | 'ø' | 'å' | 'Æ' | 'Ø' | 'Å') {
                    if new_word {
                        out.extend(ch.to_uppercase());
                    } else {
                        out.extend(ch.to_lowercase());
                    }
                    new_word = false;
                } else {
                    out.push(ch);
                    new_word = true;
                }
            }
            Ok(Some(Value::Text(out)))
        }
        "tekst_omvendt" => {
            let text = args.first().map(format_value).unwrap_or_default();
            Ok(Some(Value::Text(text.chars().rev().collect())))
        }
        "tekst_del_på" => {
            let text = args.first().map(format_value).unwrap_or_default();
            let separator = args.get(1).map(format_value).unwrap_or_default();
            let parts: Vec<Value> = if separator.is_empty() {
                vec![Value::Text(text)]
            } else {
                text.split(&separator).map(|part| Value::Text(part.to_string())).collect()
            };
            Ok(Some(Value::list(parts)))
        }
        "del_på" => {
            let text = args.first().map(format_value).unwrap_or_default();
            let separator = args.get(1).map(format_value).unwrap_or_default();
            let parts: Vec<Value> = if separator.is_empty() {
                vec![Value::Text(text)]
            } else {
                text.split(&separator).map(|part| Value::Text(part.to_string())).collect()
            };
            Ok(Some(Value::list(parts)))
        }
        "heltall_fra_tekst" => {
            let text = args.first().map(format_value).unwrap_or_default();
            let parsed = text.trim().parse::<i64>().unwrap_or(0);
            Ok(Some(Value::Int(parsed)))
        }
        "tekst_lengde" => {
            let text = args.first().map(format_value).unwrap_or_default();
            Ok(Some(Value::Int(text.chars().count() as i64)))
        }
        "tekst_slutter_med" => {
            let text = args.first().map(format_value).unwrap_or_default();
            let suffix = args.get(1).map(format_value).unwrap_or_default();
            Ok(Some(Value::Bool(text.ends_with(&suffix))))
        }
        "tekst_trim" => {
            let text = args.first().map(format_value).unwrap_or_default();
            Ok(Some(Value::Text(text.trim().to_string())))
        }
        "tekst_slice" => {
            let text = args.first().map(format_value).unwrap_or_default();
            let mut start = args
                .get(1)
                .map(runtime_int)
                .transpose()?
                .unwrap_or(0)
                .max(0) as usize;
            let mut end = args
                .get(2)
                .map(runtime_int)
                .transpose()?
                .unwrap_or_else(|| text.chars().count() as i64)
                .max(0) as usize;
            let text_len = text.chars().count();
            if start > text_len {
                start = text_len;
            }
            if end < start {
                end = start;
            }
            if end > text_len {
                end = text_len;
            }
            let slice = text
                .chars()
                .skip(start)
                .take(end.saturating_sub(start))
                .collect::<String>();
            Ok(Some(Value::Text(slice)))
        }
        "tekst_starter_med" => {
            let text = args.first().map(format_value).unwrap_or_default();
            let prefix = args.get(1).map(format_value).unwrap_or_default();
            Ok(Some(Value::Bool(text.starts_with(&prefix))))
        }
        "tekst_inneholder" => {
            let text = args.first().map(format_value).unwrap_or_default();
            let needle = args.get(1).map(format_value).unwrap_or_default();
            Ok(Some(Value::Bool(text.contains(&needle))))
        }
        "tekst_erstatt" => {
            let text = args.first().map(format_value).unwrap_or_default();
            let from = args.get(1).map(format_value).unwrap_or_default();
            let to = args.get(2).map(format_value).unwrap_or_default();
            Ok(Some(Value::Text(text.replace(&from, &to))))
        }
        "tekst_er_ordtegn" => {
            let text = args.first().map(format_value).unwrap_or_default();
            Ok(Some(Value::Bool(is_word_char(&text))))
        }
        "del_linjer" => {
            let text = args.first().map(format_value).unwrap_or_default();
            Ok(Some(Value::list(
                text.split('\n')
                    .map(|line| Value::Text(line.to_string()))
                    .collect(),
            )))
        }
        "del_ord" => {
            let text = args.first().map(format_value).unwrap_or_default();
            Ok(Some(Value::list(
                text.split_whitespace()
                    .map(|word| Value::Text(word.to_string()))
                    .collect(),
            )))
        }
        "sass_til_css" => {
            let text = args.first().map(format_value).unwrap_or_default();
            Ok(Some(Value::Text(sass_to_css(&text))))
        }
        "tokeniser_enkel" => {
            let text = args.first().map(format_value).unwrap_or_default();
            let mut tokens: Vec<String> = Vec::new();
            let mut current = String::new();
            let mut in_comment = false;
            for ch in text.chars() {
                if in_comment {
                    if ch == '\n' {
                        in_comment = false;
                    }
                    continue;
                }
                if ch == '#' {
                    if !current.is_empty() {
                        tokens.push(current.clone());
                        current.clear();
                    }
                    in_comment = true;
                    continue;
                }
                if ch.is_alphanumeric() || ch == '_' || ch == '-' {
                    current.push(ch);
                } else if !current.is_empty() {
                    tokens.push(current.clone());
                    current.clear();
                }
            }
            if !current.is_empty() {
                tokens.push(current);
            }
            Ok(Some(Value::list(tokens.into_iter().map(Value::Text).collect())))
        }
        "tokeniser_uttrykk" => {
            let text = args.first().map(format_value).unwrap_or_default();
            let tokens = tokenize_expression(&text);
            Ok(Some(Value::list(tokens.into_iter().map(Value::Text).collect())))
        }
        _ => Ok(None),
    }
}

pub(crate) fn format_value(value: &Value) -> String {
    match value {
        Value::Int(n) => n.to_string(),
        Value::Bool(v) => v.to_string(),
        Value::Text(text) => text.clone(),
        Value::List(items) => {
            let parts: Vec<String> = items.borrow().iter().map(format_value).collect();
            format!("[{}]", parts.join(", "))
        }
        Value::Null => "null".to_string(),
    }
}
