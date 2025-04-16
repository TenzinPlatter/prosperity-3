use crate::{get_log_path, get_profit};
use std::process::Command;
use std::{path::PathBuf, process::Stdio};

use crate::{
    args::Options, config::Config, create_file, get_script_path, read_file, replace_constants,
};
use rayon::prelude::*;

pub fn run_all(
    constant_strings: &Vec<String>,
    cfg: &Config,
    opts: &Options,
) -> Result<(), Box<dyn std::error::Error>> {
    let pool = match rayon::ThreadPoolBuilder::new()
        .num_threads(opts.threads as usize)
        .build()
    {
        Err(e) => return Err(e.into()),
        Ok(pool) => pool,
    };

    let mut curr_max_profit = f64::MIN;
    let mut max_constants = String::new();

    pool.install(|| {
        constant_strings
            .par_iter()
            .enumerate()
            .for_each(|(i, constants)| {
                // compare to max
                // ? update max

                let orig_script_contents = read_file(&cfg.script).unwrap();
                let new_script_contents = replace_constants(&orig_script_contents, constants);
                let new_script_path = get_script_path(i, &cfg.logs_dir);

                create_file(&new_script_contents, &new_script_path);

                let mut stdout = String::new();
                let mut stderr = String::new();

                run_script(&new_script_path, cfg.round, &mut stdout, &mut stderr);

                let log_contents: String;
                let log_path = get_log_path(i, &cfg.logs_dir);

                let profit = get_profit(&stdout);

                if let Some(profit) = profit {
                    log_contents = format!(
                        "Stdout:\n{}\n\n\nStderr:\n{}\n\n\nProfit: {}",
                        stdout, stderr, profit
                    );
                } else {
                    log_contents = format!(
                        "Stdout:\n{}\n\n\nStderr:\n{}\n\n\nNo profit found.",
                        stdout, stderr
                    );
                }

                create_file(&log_contents, &log_path);
            });
    });

    Ok(())
}

fn run_script(script_path: &PathBuf, round: u8, stdout: &mut String, stderr: &mut String) {
    let child = Command::new("prosperity3bt")
        .arg(script_path)
        .arg(round.to_string())
        .stderr(Stdio::piped())
        .stdout(Stdio::piped())
        .output()
        .expect("failed to create subprocess");

    *stdout = String::from_utf8(child.stdout).expect("stdout not valid utf8");
    *stderr = String::from_utf8(child.stderr).expect("stderr not valid utf8");
}
