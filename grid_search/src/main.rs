use clap::Parser;
use csv::Writer;
use indicatif::{ProgressBar, ProgressStyle};
use parking_lot::Mutex;
use rayon::prelude::*;
use serde::{Deserialize, Serialize};
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
const LOGS_DIR: &str = "logs";
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
}

#[derive(Serialize, Deserialize, Clone)]
struct State {
    max_profit: f64,
    constants: String,
}

#[derive(Serialize)]
struct TestResult {
    alpha_early: f64,
    alpha_late: f64,
    basespread: f64,
    adjust_scale: f64,
    max_order_early: f64,
    max_order_late: f64,
    profit: f64,
}

fn load_state() -> State {
    if !Path::new(STATE_FILE).exists() {
        let default = State {
            max_profit: f64::NEG_INFINITY,
            constants: String::new(),
        };
        save_state(&default);
        return default;
    }

    let content = std::fs::read_to_string(STATE_FILE).unwrap_or_default();
    serde_json::from_str(&content).unwrap_or_else(|e| {
        eprintln!("Corrupt state file: {}", e);
        State {
            max_profit: f64::NEG_INFINITY,
            constants: String::new(),
        }
    })
}

fn save_state(state: &State) {
    let serialized = serde_json::to_string_pretty(state).unwrap();
    std::fs::write(STATE_FILE, serialized).unwrap();
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

fn create_script_with_constants(constants: &str, index: usize) -> std::io::Result<String> {
    let file = read_to_string(TARGET_FILE)?;
    let mut lines: Vec<_> = file.lines().map(String::from).collect();

    let start = lines.iter().position(|l| l.contains("# start")).unwrap();
    let end = lines.iter().position(|l| l.contains("# end")).unwrap();

    if start >= end {
        panic!("Invalid start/end block");
    }

    let mut new_lines = lines[..=start].to_vec();
    new_lines.push(constants.to_string());
    new_lines.extend_from_slice(&lines[end..]);

    let script_path = get_script_path(index);
    let script_dir = Path::new(&script_path).parent().unwrap();
    std::fs::create_dir_all(script_dir)?;
    write(&script_path, new_lines.join("\n"))?;
    Ok(script_path)
}

fn get_script_path(index: usize) -> String {
    let subdir = (index / 100) * 100;
    format!(
        "{}/{}-{}/{}/script_{}.py",
        LOGS_DIR,
        subdir,
        subdir + 99,
        SCRIPTS_SUBDIR,
        index
    )
}

fn get_log_path(index: usize) -> String {
    let subdir = (index / 100) * 100;
    format!(
        "{}/{}-{}/{}/log_{}.txt",
        LOGS_DIR,
        subdir,
        subdir + 99,
        OUTPUT_SUBDIR,
        index
    )
}

fn ensure_directories() -> std::io::Result<()> {
    // Create .logs directory and its subdirectories
    for i in 0..=9 {
        // Assuming we'll have up to 1000 scripts
        let subdir = i * 100;
        let subdir_path = format!("{}/{}-{}", LOGS_DIR, subdir, subdir + 99);
        std::fs::create_dir_all(format!("{}/{}", subdir_path, SCRIPTS_SUBDIR))?;
        std::fs::create_dir_all(format!("{}/{}", subdir_path, OUTPUT_SUBDIR))?;
    }
    
    Ok(())
}

fn cleanup_directory() -> std::io::Result<()> {
    // Clean up log files in each subdirectory
    for i in 0..=9 {
        let subdir = i * 100;
        let subdir_path = format!("{}/{}-{}", LOGS_DIR, subdir, subdir + 99);
        
        // Clean scripts directory
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
        
        // Clean output directory
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

fn run_and_get_profit(constants: &str, index: usize) -> Result<f64, Box<dyn std::error::Error>> {
    let script_path = create_script_with_constants(constants, index)?;
    let log_path = get_log_path(index);
    let mut log_file = std::fs::File::create(&log_path)?;

    writeln!(log_file, "Script Index: {}", index)?;
    writeln!(log_file, "Constants:\n{}", constants)?;
    writeln!(log_file, "Script Path: {}", script_path)?;
    writeln!(log_file, "Command: prosperity3bt {} 0", script_path)?;

    let output = Command::new("prosperity3bt")
        .arg(script_path)
        .arg("0")
        .output()
        .expect("Failed to execute command");

    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);

    writeln!(log_file, "Command Status: {}", output.status)?;
    writeln!(log_file, "stdout:\n{}", stdout)?;
    writeln!(log_file, "stderr:\n{}", stderr)?;

    if let Some(profit) = parse_profit(&stdout) {
        writeln!(log_file, "Profit: ${:.2}", profit)?;
        Ok(profit)
    } else {
        writeln!(log_file, "Profit: N/A (no profit found in output)")?;
        writeln!(log_file, "Raw output for debugging:\n{}", stdout)?;
        Ok(0.0)
    }
}

fn validate_target_file() -> Result<(), &'static str> {
    let content = std::fs::read_to_string(TARGET_FILE).map_err(|_| "Cannot read target file")?;
    if !content.contains("# start") || !content.contains("# end") {
        return Err("Target file must contain '# start' and '# end'");
    }
    Ok(())
}

fn parse_constants(constants: &str) -> Option<TestResult> {
    let mut result = TestResult {
        alpha_early: 0.0,
        alpha_late: 0.0,
        basespread: 0.0,
        adjust_scale: 0.0,
        max_order_early: 0.0,
        max_order_late: 0.0,
        profit: 0.0,
    };

    for line in constants.lines() {
        let parts: Vec<&str> = line.split('=').map(|s| s.trim()).collect();
        if parts.len() != 2 {
            continue;
        }
        let value = parts[1].parse::<f64>().ok()?;
        match parts[0] {
            "ALPHA_EARLY" => result.alpha_early = value,
            "ALPHA_LATE" => result.alpha_late = value,
            "BASESPREAD" => result.basespread = value,
            "ADJUST_SCALE" => result.adjust_scale = value,
            "MAX_ORDER_EARLY" => result.max_order_early = value,
            "MAX_ORDER_LATE" => result.max_order_late = value,
            _ => continue,
        }
    }
    Some(result)
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let start_time = Instant::now();
    let args = Args::parse();
    validate_target_file()?;
    
    // Set number of threads if specified
    if let Some(threads) = args.threads {
        rayon::ThreadPoolBuilder::new()
            .num_threads(threads)
            .build_global()
            .expect("Failed to set number of threads");
    }
    
    let num_threads = rayon::current_num_threads();
    println!("Using {} threads", num_threads);
    
    // Ensure all directories exist
    ensure_directories()?;

    // Clean up old files
    cleanup_directory()?;

    // Create CSV file in the root directory
    let csv_file = File::create(CSV_FILE)?;
    let csv_writer = Arc::new(Mutex::new(Writer::from_writer(csv_file)));
    csv_writer.lock().write_record(&[
        "alpha_early",
        "alpha_late",
        "basespread",
        "adjust_scale",
        "max_order_early",
        "max_order_late",
        "profit",
    ])?;

    let state = Arc::new(Mutex::new(load_state()));

    println!("Creating constants");
    io::stdout().flush().unwrap();

    let mut constants_list = Vec::new();

    // ALPHA_EARLY: Controls early phase order adjustment (0.1% to 0.5%)
    let alpha_early_steps = [0.001, 0.002, 0.003, 0.004, 0.005];

    // ALPHA_LATE: Controls late phase order adjustment (0.2% to 1.0%)
    let alpha_late_steps = [0.002, 0.004, 0.006, 0.008, 0.01];

    // BASESPREAD: Base spread for orders (0.5% to 2.5%)
    let basespread_steps = [0.005, 0.01, 0.015, 0.02, 0.025];

    // ADJUST_SCALE: Scale for position adjustments (0.1 to 0.5)
    let adjust_scale_steps = [0.1, 0.2, 0.3, 0.4, 0.5];

    // MAX_ORDER_EARLY: Maximum order size early phase (10% to 50% of position)
    let max_order_early_steps = [0.1, 0.2, 0.3, 0.4, 0.5];

    // MAX_ORDER_LATE: Maximum order size late phase (5% to 25% of position)
    let max_order_late_steps = [0.05, 0.1, 0.15, 0.2, 0.25];

    for &a_e in &alpha_early_steps {
        for &a_l in &alpha_late_steps {
            for &adj in &adjust_scale_steps {
                for &base in &basespread_steps {
                    for &max_e in &max_order_early_steps {
                        for &max_l in &max_order_late_steps {
                            constants_list.push(format!(
                                "ALPHA_EARLY = {}\nALPHA_LATE = {}\nBASESPREAD = {}\nADJUST_SCALE = {}\nMAX_ORDER_EARLY = {}\nMAX_ORDER_LATE = {}",
                                a_e,
                                a_l,
                                base,
                                adj,
                                max_e,
                                max_l,
                            ));
                        }
                    }
                }
            }
        }
    }

    println!("Running {} combinations", constants_list.len());
    io::stdout().flush().unwrap();

    let pb = ProgressBar::new(constants_list.len() as u64);
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
                let profit = run_and_get_profit(constants, global_index).unwrap_or(0.0);
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
                save_state(&state);
            }

            if let Some(mut result) = parse_constants(&constants) {
                result.profit = profit;
                let mut writer_lock = csv_writer.lock();
                writer_lock
                    .serialize(&result)
                    .expect("Failed to write to CSV");
                writer_lock.flush().expect("Failed to flush CSV writer");
            }
        }
    }

    pb.finish_with_message("Search complete");
    let duration = start_time.elapsed();
    println!("Total time: {:.2?}", duration);
    println!("Best result saved to {}", STATE_FILE);
    if args.test {
        println!("All results saved to {}", CSV_FILE);
    }
    Ok(())
}
