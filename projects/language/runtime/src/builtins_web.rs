use crate::builtins_text::{format_value, sass_to_css};
use crate::error::RuntimeError;
use crate::stdio::Io;
use crate::value::Value;
use crate::vm::Vm;
use std::collections::BTreeMap;
use std::io::{BufRead, BufReader, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::str::FromStr;

pub(crate) fn handle_web_builtin<I: Io>(
    vm: &mut Vm<I>,
    name: &str,
    args: &[Value],
) -> Result<Option<Value>, RuntimeError> {
    match name {
        "bootstrap_html" => {
            let title = args.first().map(format_value).unwrap_or_default();
            let heading = args.get(1).map(format_value).unwrap_or_default();
            let ingress = args.get(2).map(format_value).unwrap_or_default();
            let button = args.get(3).map(format_value).unwrap_or_default();
            Ok(Some(Value::Text(format!(
                "<!doctype html>\n\
<html lang=\"no\">\n\
<head>\n\
    <meta charset=\"utf-8\">\n\
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n\
    <title>{title}</title>\n\
    <link href=\"https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css\" rel=\"stylesheet\">\n\
    <link rel=\"stylesheet\" href=\"styles.css\">\n\
</head>\n\
<body class=\"bg-light\">\n\
    <main class=\"container py-5\">\n\
        <section class=\"card shadow border-0 rounded-4 p-5 bg-white\">\n\
            <h1 class=\"display-5 fw-bold\">{heading}</h1>\n\
            <p class=\"lead\">{ingress}</p>\n\
            <button class=\"btn btn-primary\">{button}</button>\n\
        </section>\n\
    </main>\n\
</body>\n\
</html>\n"
            ))))
        }
        "css_startmal" => Ok(Some(Value::Text(
            "body {\n    margin: 0;\n    font-family: system-ui, sans-serif;\n    background: #f8fafc;\n    color: #0f172a;\n}\n\nmain {\n    max-width: 960px;\n    margin: 0 auto;\n    padding: 48px 24px;\n}\n\n.card {\n    border: 0;\n    box-shadow: 0 12px 30px rgba(15, 23, 42, 0.15);\n}\n"
                .to_string(),
        ))),
        "sass_startmal" => Ok(Some(Value::Text(
            "$bg: #0f172a;\n$panel: #111827;\n$accent: #60a5fa;\n\nbody {\n    margin: 0;\n    font-family: system-ui, sans-serif;\n    background: $bg;\n    color: #e2e8f0;\n}\n\nmain {\n    max-width: 960px;\n    margin: 0 auto;\n    padding: 48px 24px;\n}\n\n.card {\n    background: $panel;\n    border-radius: 24px;\n    padding: 32px;\n    box-shadow: 0 12px 30px rgba(15, 23, 42, 0.25);\n\n    button {\n        background: $accent;\n        border: 0;\n        border-radius: 999px;\n        color: $bg;\n        padding: 12px 18px;\n        font-weight: 700;\n    }\n}\n"
                .to_string(),
        ))),
        "sass_til_css_tekst" => {
            let source = args.first().map(format_value).unwrap_or_default();
            Ok(Some(Value::Text(sass_to_css(&source))))
        }
        "css_trim" => {
            let text = args.first().map(format_value).unwrap_or_default();
            Ok(Some(Value::Text(text.trim().to_string())))
        }
        "web_server_start" => {
            let routes = parse_routes(args.first());
            let host = args.get(1).map(format_value).unwrap_or_else(|| "127.0.0.1".to_string());
            let port = args
                .get(2)
                .map(format_value)
                .and_then(|value| value.parse::<u16>().ok())
                .unwrap_or(8000);
            start_web_server(vm, routes, host, port)?;
            Ok(Some(Value::Int(0)))
        }
        _ => Ok(None),
    }
}

#[derive(Debug, Clone)]
struct HttpRoute {
    method: String,
    pattern: String,
    handler: String,
}

#[derive(Debug, Clone)]
struct HttpRequest {
    method: String,
    path: String,
    query: String,
    body: String,
}

fn parse_routes(value: Option<&Value>) -> Vec<HttpRoute> {
    let Some(Value::List(items)) = value else {
        return Vec::new();
    };
    items
        .borrow()
        .iter()
        .filter_map(|item| match item {
            Value::Text(text) => {
                let parts: Vec<&str> = if text.contains('\t') {
                    text.split('\t').collect()
                } else {
                    text.split('|').collect()
                };
                if parts.len() >= 3 {
                    Some(HttpRoute {
                        method: parts[0].to_string(),
                        pattern: parts[1].to_string(),
                        handler: parts[2].to_string(),
                    })
                } else {
                    None
                }
            }
            _ => None,
        })
        .collect()
}

fn start_web_server<I: Io>(
    vm: &mut Vm<I>,
    routes: Vec<HttpRoute>,
    host: String,
    port: u16,
) -> Result<(), RuntimeError> {
    let listener = TcpListener::bind((host.as_str(), port))
        .map_err(|err| RuntimeError::IoError(err.to_string()))?;
    for connection in listener.incoming() {
        let mut stream = connection.map_err(|err| RuntimeError::IoError(err.to_string()))?;
        if let Err(err) = handle_web_connection(vm, &routes, &mut stream) {
            let _ = write_plain_response(
                &mut stream,
                500,
                "Internal Server Error",
                &format!("Feil: {err}"),
            );
        }
    }
    Ok(())
}

fn handle_web_connection<I: Io>(
    vm: &mut Vm<I>,
    routes: &[HttpRoute],
    stream: &mut TcpStream,
) -> Result<(), RuntimeError> {
    let request = read_http_request(stream)?;
    let response = dispatch_http_request(vm, routes, &request)?;
    if request.method == "HEAD" {
        let head_response = head_response_text(&response);
        stream
            .write_all(head_response.as_bytes())
            .map_err(|err| RuntimeError::IoError(err.to_string()))?;
    } else if response.starts_with("HTTP/1.1 ") {
        stream
            .write_all(response.as_bytes())
            .map_err(|err| RuntimeError::IoError(err.to_string()))?;
    } else {
        write_plain_response(stream, 200, "OK", &response)?;
    }
    stream.flush().map_err(|err| RuntimeError::IoError(err.to_string()))?;
    Ok(())
}

fn dispatch_http_request<I: Io>(
    vm: &mut Vm<I>,
    routes: &[HttpRoute],
    request: &HttpRequest,
) -> Result<String, RuntimeError> {
    for route in routes {
        if method_matches(&route.method, &request.method) && path_match(&route.pattern, &request.path) {
            let response = vm.invoke_function(
                &route.handler,
                vec![
                    Value::Text(request.method.clone()),
                    Value::Text(request.path.clone()),
                    Value::Text(request.query.clone()),
                    Value::Text(request.body.clone()),
                ],
            )?;
            return Ok(match response {
                Value::Text(text) => text,
                other => format_value(&other),
            });
        }
    }
    Ok(http_response_text(404, "Not Found", "Not Found"))
}

fn method_matches(route_method: &str, request_method: &str) -> bool {
    route_method == request_method || (request_method == "HEAD" && route_method == "GET")
}

fn read_http_request(stream: &TcpStream) -> Result<HttpRequest, RuntimeError> {
    let mut reader = BufReader::new(
        stream
            .try_clone()
            .map_err(|err| RuntimeError::IoError(err.to_string()))?,
    );
    let mut request_line = String::new();
    reader
        .read_line(&mut request_line)
        .map_err(|err| RuntimeError::IoError(err.to_string()))?;
    if request_line.trim().is_empty() {
        return Err(RuntimeError::InvalidOperand("tom HTTP-forespørsel".to_string()));
    }
    let mut parts = request_line.trim_end_matches(['\r', '\n']).split_whitespace();
    let method = parts.next().unwrap_or("").to_string();
    let target = parts.next().unwrap_or("").to_string();
    let mut headers = BTreeMap::new();
    loop {
        let mut line = String::new();
        reader
            .read_line(&mut line)
            .map_err(|err| RuntimeError::IoError(err.to_string()))?;
        let trimmed = line.trim_end_matches(['\r', '\n']);
        if trimmed.is_empty() {
            break;
        }
        if let Some((name, value)) = trimmed.split_once(':') {
            headers.insert(name.trim().to_lowercase(), value.trim().to_string());
        }
    }
    let body_len = headers
        .get("content-length")
        .and_then(|value| usize::from_str(value).ok())
        .unwrap_or(0);
    let mut body_bytes = vec![0u8; body_len];
    if body_len > 0 {
        reader
            .read_exact(&mut body_bytes)
            .map_err(|err| RuntimeError::IoError(err.to_string()))?;
    }
    let body = String::from_utf8(body_bytes).unwrap_or_default();
    let (path, query) = match target.split_once('?') {
        Some((path, query)) => (path.to_string(), query.to_string()),
        None => (target, String::new()),
    };
    Ok(HttpRequest {
        method,
        path,
        query,
        body,
    })
}

fn path_match(pattern: &str, path: &str) -> bool {
    let pattern_segments = split_segments(pattern);
    let path_segments = split_segments(path);
    if pattern_segments.len() != path_segments.len() {
        return false;
    }
    pattern_segments
        .iter()
        .zip(path_segments.iter())
        .all(|(left, right)| is_path_param(left) || left == right)
}

fn split_segments(value: &str) -> Vec<&str> {
    value.split('/').filter(|segment| !segment.is_empty()).collect()
}

fn is_path_param(segment: &str) -> bool {
    segment.starts_with('{') && segment.ends_with('}')
}

fn write_plain_response(
    stream: &mut TcpStream,
    code: u16,
    status: &str,
    body: &str,
) -> Result<(), RuntimeError> {
    let response = http_response_text(code, status, body);
    stream
        .write_all(response.as_bytes())
        .map_err(|err| RuntimeError::IoError(err.to_string()))?;
    Ok(())
}

fn http_response_text(code: u16, status: &str, body: &str) -> String {
    format!(
        "HTTP/1.1 {code} {status}\r\nContent-Type: text/plain; charset=utf-8\r\nContent-Length: {}\r\n\r\n{}",
        body.len(),
        body
    )
}

fn head_response_text(response: &str) -> String {
    let Some((head, _body)) = response.split_once("\r\n\r\n") else {
        return response.to_string();
    };
    let mut lines = head.lines();
    let Some(status_line) = lines.next() else {
        return response.to_string();
    };
    let mut out = String::new();
    out.push_str(status_line);
    out.push_str("\r\n");
    let mut saw_content_length = false;
    for line in lines {
        if line.to_ascii_lowercase().starts_with("content-length:") {
            out.push_str("Content-Length: 0\r\n");
            saw_content_length = true;
        } else {
            out.push_str(line);
            out.push_str("\r\n");
        }
    }
    if !saw_content_length {
        out.push_str("Content-Length: 0\r\n");
    }
    out.push_str("\r\n");
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn path_match_supports_parameters() {
        assert!(path_match("/api/tickets/{id}", "/api/tickets/42"));
        assert!(!path_match("/api/tickets/{id}", "/api/users/42"));
    }

    #[test]
    fn head_matches_get_routes() {
        assert!(method_matches("GET", "HEAD"));
        assert!(method_matches("GET", "GET"));
        assert!(!method_matches("POST", "HEAD"));
    }

    #[test]
    fn head_response_removes_body_and_sets_zero_length() {
        let response = "HTTP/1.1 200 OK\r\nContent-Type: text/plain; charset=utf-8\r\nContent-Length: 5\r\n\r\nhello";
        let head_response = head_response_text(response);
        assert!(head_response.starts_with("HTTP/1.1 200 OK\r\n"));
        assert!(head_response.contains("Content-Length: 0\r\n"));
        assert!(!head_response.contains("hello"));
    }
}
