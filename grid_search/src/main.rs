use clap::Parser;
use indicatif::{ProgressBar, ProgressStyle};
use parking_lot::Mutex;
use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::io::{self, Write};
use std::{
    fs::{File, create_dir_all, read_dir, read_to_string, write},
    path::Path,
    process::Command,
    sync::Arc,
    time::Instant,
};
use wait_timeout::ChildExt;

const TARGET_FILE: &str = "../trader_resin_draft.py";
const STATE_FILE: &str = "../best.json";
const SCRIPTS_SUBDIR: &str = "scripts";
const OUTPUT_SUBDIR: &str = "output";
const CSV_FILE: &str = "grid_search_results.csv";

#[derive(Parser, Debug)]
#[command(author, version, about, long_about = None)]
struct Args {
    /// Enable testing mode to save all results to CSV
    #[arg(short = 'e', long)]
    test: bool,

    /// Number of threads to use (default: number of CPU cores)
    #[arg(short = 'j', long)]
    threads: Option<usize>,

    /// Path to config file (default: config.json)
    #[arg(short = 'c', long, default_value = "config.json")]
    config: String,
}

#[derive(Serialize, Deserialize, Clone)]
struct State {
    max_profit: f64,
    constants: String,
}

#[derive(Deserialize, Debug)]
struct ParameterRange {
    start: f64,
    end: f64,
    step: f64,
}

#[derive(Deserialize, Debug)]
struct Config {
    python_script: String,
    logs_dir: String,
    state_file: String,
    parameters: HashMap<String, ParameterRange>,
}

impl Config {
    fn load(config_path: &str) -> Result<Self, Box<dyn std::error::Error>> {
        let config_str = std::fs::read_to_string(config_path)
            .map_err(|e| format!("Failed to read config file '{}': {}", config_path, e))?;
        let config: Config = serde_json::from_str(&config_str)
            .map_err(|e| format!("Failed to parse config file '{}': {}", config_path, e))?;
        Ok(config)
    }

    fn generate_values(&self, param: &ParameterRange) -> Vec<f64> {
        let mut values = Vec::new();
        let mut current = param.start;
        while current <= param.end {
            values.push(current);
            current += param.step;
        }
        values
    }
}

#[derive(Serialize)]
struct TestResult {
    parameters: HashMap<String, f64>,
    profit: f64,
}

fn load_state(config: &Config) -> State {
    if !Path::new(&config.state_file).exists() {
        let default = State {
            max_profit: f64::NEG_INFINITY,
            constants: String::new(),
        };
        save_state(&default, config);
        return default;
    }

    let content = std::fs::read_to_string(&config.state_file).unwrap_or_default();
    serde_json::from_str(&content).unwrap_or_else(|e| {
        eprintln!("Corrupt state file: {}", e);
        State {
            max_profit: f64::NEG_INFINITY,
            constants: String::new(),
        }
    })
}

fn save_state(state: &State, config: &Config) {
    let serialized = serde_json::to_string_pretty(state).unwrap();
    std::fs::write(&config.state_file, serialized).unwrap();
}

fn parse_profit(output: &str) -> Option<f64> {
    for line in output.lines() {
        if line.contains("Total profit") {
            let parts: Vec<&str> = line.split_whitespace().collect();
            if let Some(profit_str) = parts.last() {
                // Remove any commas from the number
                let clean = profit_str.replace(",", "");
                match clean.parse::<f64>() {
                    Ok(profit) => {
                        return Some(profit);
                    }
                    Err(e) => {
                        eprintln!(
                            "Failed to parse profit '{}' (cleaned: '{}'): {}",
                            profit_str, clean, e
                        );
                    }
                }
            }
        }
    }
    None
}

fn get_script_path(index: usize, logs_dir: &str) -> String {
    let subdir = (index / 100) * 100;
    format!(
        "{}/{}-{}/{}/script_{}.py",
        logs_dir,
        subdir,
        subdir + 99,
        SCRIPTS_SUBDIR,
        index
    )
}

fn get_log_path(index: usize, logs_dir: &str) -> String {
    let subdir = (index / 100) * 100;
    format!(
        "{}/{}-{}/{}/log_{}.txt",
        logs_dir,
        subdir,
        subdir + 99,
        OUTPUT_SUBDIR,
        index
    )
}

fn ensure_directories(total_scripts: usize, logs_dir: &str) -> std::io::Result<()> {
    let num_dirs = (total_scripts + 99) / 100;
    for i in 0..num_dirs {
        let subdir = i * 100;
        let subdir_path = format!("{}/{}-{}", logs_dir, subdir, subdir + 99);
        let scripts_dir = format!("{}/{}", subdir_path, SCRIPTS_SUBDIR);
        let output_dir = format!("{}/{}", subdir_path, OUTPUT_SUBDIR);

        std::fs::create_dir_all(&scripts_dir)?;
        std::fs::create_dir_all(&output_dir)?;
    }
    Ok(())
}

fn cleanup_directory(total_scripts: usize, logs_dir: &str) -> std::io::Result<()> {
    let num_dirs = (total_scripts + 99) / 100;
    for i in 0..num_dirs {
        let subdir = i * 100;
        let subdir_path = format!("{}/{}-{}", logs_dir, subdir, subdir + 99);

        let scripts_dir = format!("{}/{}", subdir_path, SCRIPTS_SUBDIR);
        if Path::new(&scripts_dir).exists() {
            for entry in std::fs::read_dir(&scripts_dir)? {
                let entry = entry?;
                let path = entry.path();
                if path.is_file() {
                    std::fs::remove_file(path)?;
                }
            }
        }

        let output_dir = format!("{}/{}", subdir_path, OUTPUT_SUBDIR);
        if Path::new(&output_dir).exists() {
            for entry in std::fs::read_dir(&output_dir)? {
                let entry = entry?;
                let path = entry.path();
                if path.is_file() {
                    std::fs::remove_file(path)?;
                }
            }
        }
    }
    Ok(())
}

fn create_script_with_constants(
    constants: &str,
    index: usize,
    config: &Config,
) -> std::io::Result<String> {
    let file = read_to_string(&config.python_script)?;
    let mut lines: Vec<_> = file.lines().map(String::from).collect();

    let start = lines.iter().position(|l| l.contains("# start")).unwrap();
    let end = lines.iter().position(|l| l.contains("# end")).unwrap();

    if start >= end {
        panic!("Invalid start/end block");
    }

    let mut new_lines = lines[..=start].to_vec();
    new_lines.push(constants.to_string());
    new_lines.extend_from_slice(&lines[end..]);

    let script_path = get_script_path(index, &config.logs_dir);
    let script_dir = Path::new(&script_path).parent().unwrap();
    std::fs::create_dir_all(script_dir)?;
    write(&script_path, new_lines.join("\n"))?;
    Ok(script_path)
}

fn run_and_get_profit(
    constants: &str,
    index: usize,
    config: &Config,
) -> Result<f64, Box<dyn std::error::Error>> {
    let script_path = create_script_with_constants(constants, index, config)?;
    let log_path = get_log_path(index, &config.logs_dir);
    let log_dir = Path::new(&log_path).parent().unwrap();
    std::fs::create_dir_all(log_dir)?;

    let mut log_file = std::fs::File::create(&log_path)?;

    writeln!(log_file, "Script Index: {}", index)?;
    writeln!(log_file, "Constants:\n{}", constants)?;
    writeln!(log_file, "Script Path: {}", script_path)?;
    writeln!(log_file, "Command: prosperity3bt {} 0", script_path)?;
    log_file.flush()?;

    let mut child = Command::new("prosperity3bt")
        .arg(&script_path)
        .arg("3")
        .stderr(std::process::Stdio::null())
        .spawn()
        .expect("Failed to start command");

    // Wait for the process with a timeout
    let timeout = std::time::Duration::from_secs(30);
    let status = match child.wait_timeout(timeout)? {
        Some(status) => status,
        None => {
            // Process timed out, kill it
            child.kill()?;
            child.wait()?;
            writeln!(
                log_file,
                "Command timed out after {} seconds",
                timeout.as_secs()
            )?;
            log_file.flush()?;
            return Ok(0.0);
        }
    };

    let output = child.wait_with_output()?;
    let stdout = String::from_utf8_lossy(&output.stdout);

    writeln!(log_file, "Command Status: {}", status)?;
    writeln!(log_file, "stdout:\n{}", stdout)?;

    if let Some(profit) = parse_profit(&stdout) {
        writeln!(log_file, "Profit: ${:.2}", profit)?;
    } else {
        writeln!(log_file, "Profit: N/A (no profit found in output)")?;
        writeln!(log_file, "Raw output for debugging:\n{}", stdout)?;
    }
    log_file.flush()?;

    if !status.success() {
        writeln!(log_file, "Command failed with status: {}", status)?;
        log_file.flush()?;
        return Ok(0.0);
    }

    parse_profit(&stdout).ok_or_else(|| "Failed to parse profit".into())
}

fn validate_target_file(config: &Config) -> Result<(), &'static str> {
    let content =
        std::fs::read_to_string(&config.python_script).map_err(|_| "Cannot read target file")?;
    if !content.contains("# start") || !content.contains("# end") {
        return Err("Target file must contain '# start' and '# end'");
    }
    Ok(())
}

fn parse_constants(constants: &str, param_names: &[&String]) -> Option<TestResult> {
    let mut param_map = HashMap::new();

    for line in constants.lines() {
        let parts: Vec<&str> = line.split('=').map(|s| s.trim()).collect();
        if parts.len() != 2 {
            continue;
        }
        if let Ok(value) = parts[1].parse::<f64>() {
            param_map.insert(parts[0].to_string(), value);
        }
    }

    Some(TestResult {
        parameters: param_map,
        profit: 0.0,
    })
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let start_time = Instant::now();
    let args = Args::parse();

    // Load configuration
    let config = Config::load(&args.config)?;
    validate_target_file(&config)?;

    // Set number of threads if specified
    if let Some(threads) = args.threads {
        rayon::ThreadPoolBuilder::new()
            .num_threads(threads)
            .build_global()
            .expect("Failed to set number of threads");
    }

    let num_threads = rayon::current_num_threads();
    println!("Using {} threads", num_threads);

    // Generate constants list using configuration
    let mut constants_list = Vec::new();

    // Get all possible values for each parameter
    let param_values: HashMap<_, _> = config
        .parameters
        .iter()
        .map(|(name, range)| (name, config.generate_values(range)))
        .collect();

    // Generate all combinations
    let param_names: Vec<_> = config.parameters.keys().collect();
    let mut indices: Vec<_> = param_names.iter().map(|_| 0).collect();
    let sizes: Vec<_> = param_names
        .iter()
        .map(|&name| param_values[name].len())
        .collect();

    loop {
        let mut constant_str = String::new();
        for (i, &name) in param_names.iter().enumerate() {
            let value = param_values[name][indices[i]];
            constant_str.push_str(&format!("{} = {}\n", name, value));
        }
        constants_list.push(constant_str);

        // Update indices
        let mut j = indices.len();
        loop {
            if j == 0 {
                // All combinations done
                break;
            }
            j -= 1;
            indices[j] += 1;
            if indices[j] < sizes[j] {
                break;
            }
            indices[j] = 0;
        }
        if j == 0 && indices[0] == 0 {
            break;
        }
    }

    let total_combinations = constants_list.len();
    println!("Generated {} combinations", total_combinations);

    // Ensure all directories exist
    ensure_directories(total_combinations, &config.logs_dir)?;

    // Clean up old files
    cleanup_directory(total_combinations, &config.logs_dir)?;

    let state = Arc::new(Mutex::new(load_state(&config)));

    println!("Starting grid search...");
    io::stdout().flush().unwrap();

    let pb = ProgressBar::new(total_combinations as u64);
    pb.set_style(
        ProgressStyle::default_bar()
            .template("[{elapsed_precise}] [{bar:40.cyan/blue}] {pos}/{len} ({eta}) {per_sec}")
            .unwrap()
            .progress_chars("##-"),
    );

    // Process in chunks to avoid memory issues
    let chunk_size = 100;
    let mut best_profit = f64::NEG_INFINITY;
    let mut best_constants = String::new();

    for (chunk_index, chunk) in constants_list.chunks(chunk_size).enumerate() {
        let results: Vec<_> = chunk
            .par_iter()
            .enumerate()
            .map(|(i, constants)| {
                let global_index = chunk_index * chunk_size + i;
                let profit = run_and_get_profit(constants, global_index, &config).unwrap_or(0.0);
                pb.inc(1);
                (profit, constants.clone())
            })
            .collect();

        for (profit, constants) in results {
            if profit > best_profit {
                best_profit = profit;
                best_constants = constants.clone();
                println!("\n[NEW MAX] {:.2} with:\n{}\n", profit, constants);

                let state = State {
                    max_profit: profit,
                    constants: constants.clone(),
                };
                save_state(&state, &config);
            }
        }
    }

    pb.finish_with_message("Search complete");
    let duration = start_time.elapsed();
    println!("Total time: {:.2?}", duration);
    println!("Best result saved to {}", config.state_file);
    Ok(())
}
