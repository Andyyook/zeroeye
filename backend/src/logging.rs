pub fn resolve_log_format() -> Result<&'static str, String> {
    resolve_log_format_from(std::env::var("TOT_LOG_FORMAT").as_deref().ok())
}

pub fn resolve_log_format_from(value: Option<&str>) -> Result<&'static str, String> {
    match value {
        None | Some("") | Some("text") => Ok("text"),
        Some("json") => Ok("json"),
        Some(other) => Err(format!("invalid TOT_LOG_FORMAT value: {}", other)),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn defaults_to_text_when_unset() {
        assert_eq!(resolve_log_format_from(None).unwrap(), "text");
    }

    #[test]
    fn accepts_text() {
        assert_eq!(resolve_log_format_from(Some("text")).unwrap(), "text");
    }

    #[test]
    fn accepts_json() {
        assert_eq!(resolve_log_format_from(Some("json")).unwrap(), "json");
    }

    #[test]
    fn rejects_invalid_value() {
        assert!(resolve_log_format_from(Some("xml")).is_err());
    }
}
