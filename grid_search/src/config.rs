use serde::{Deserialize, Serialize};

use crate::read_file;

#[derive(Serialize, Deserialize, Debug)]
pub struct Config {
    pub script: String,
    pub variables: Vec<VariableConfig>,
    pub logs_dir: String,
    pub round: u8,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct VariableConfig {
    pub name: String,
    pub start: f64,
    pub end: f64,
    pub step: f64,
}

pub fn parse_config(fp: &str) -> Result<Config, Box<dyn std::error::Error>> {
    let contents = read_file(fp)?;

    let config: Config = serde_json::from_str(&contents)?;

    return Ok(config);
}
