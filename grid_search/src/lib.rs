pub mod args;
pub mod config;
pub mod float_range;
pub mod run;

use std::{
    fs::{self, File},
    io::Write,
    option::Option,
    path::{Path, PathBuf},
};

use config::VariableConfig;
use float_range::FloatRange;
use regex::Regex;

pub fn create_or_clean_logs_dir(path: &Path, num_of_combinations: usize) {
    if path.exists() {
        fs::remove_dir_all(path).unwrap();
    }

    let dir_limit = ((num_of_combinations + 99) / 100) * 100;

    for i in (0..dir_limit).step_by(100) {
        let start = i;
        let end = i + 99;

        let subdir = path.join(format!("{}-{}", start, end));

        fs::create_dir_all(subdir.join("logs")).unwrap();
        fs::create_dir_all(subdir.join("scripts")).unwrap();
    }
}

pub fn get_profit(output: &str) -> Option<f64> {
    let re = Regex::new(r"Total profit:\s*([\d,]+)").unwrap();

    re.captures(output).and_then(|caps| {
        caps.get(1)
            .map(|m| {
                let clean = m.as_str().replace(",", "");
                clean.parse::<f64>().ok()
            })
            .flatten()
    })
}

pub fn get_log_path(i: usize, logs_dir: &str) -> PathBuf {
    let logs_dir = Path::new(logs_dir);

    let idx_range_start = (i / 100) * 100;
    let idx_range_end = idx_range_start + 99;

    let log_subdir = format!("{}-{}", idx_range_start, idx_range_end);
    let log_fp_leaf = format!("log_{}.txt", i);

    logs_dir.join(log_subdir).join("logs").join(log_fp_leaf)
}

pub fn create_file(contents: &str, path: &PathBuf) {
    let display = path.display();
    let mut file = match File::create(&path) {
        Ok(file) => file,
        Err(why) => panic!("couldn't create {}: {}", display, why),
    };

    if let Err(why) = file.write_all(contents.as_bytes()) {
        panic!("couldn't write to {}: {}", display, why);
    }
}

pub fn get_script_path(i: usize, logs_dir: &str) -> PathBuf {
    let logs_dir = Path::new(logs_dir);

    let idx_range_start = (i / 100) * 100;
    let idx_range_end = idx_range_start + 99;

    let script_subdir = format!("{}-{}", idx_range_start, idx_range_end);
    let script_fp_leaf = format!("script_{}.py", i);

    logs_dir
        .join(script_subdir)
        .join("scripts")
        .join(script_fp_leaf)
}

pub fn replace_constants(script_contents: &str, new_constants: &str) -> String {
    let re = Regex::new(r"(?s)# start.*?# end").unwrap();

    re.replace(script_contents, format!("# start\n{}\n#end", new_constants))
        .to_string()
}

pub fn read_file(fp: &str) -> Result<String, Box<dyn std::error::Error>> {
    let path = Path::new(fp);
    let contents = fs::read_to_string(path)?;
    Ok(contents)
}

pub fn get_constant_strings(vars: &Vec<VariableConfig>) -> Vec<String> {
    let loop_ranges = generate_loops(&vars);

    generate_combinations(&loop_ranges, &vars)
}

fn generate_loops(vars: &Vec<VariableConfig>) -> Vec<FloatRange> {
    let mut res = Vec::new();

    for var in vars {
        res.push(FloatRange::new(var.start, var.end, var.step));
    }

    res
}

fn generate_combinations(ranges: &[FloatRange], vars: &Vec<VariableConfig>) -> Vec<String> {
    fn helper(
        ranges: &[FloatRange],
        index: usize,
        current: &mut Vec<f64>,
        output: &mut Vec<String>,
        vars: &Vec<VariableConfig>,
    ) {
        if index == ranges.len() {
            let combo = current
                .iter()
                .enumerate()
                .map(|(i, v)| format!("{} = {:.3}", vars[i].name, v))
                .collect::<Vec<_>>()
                .join("\n");
            output.push(combo);
            return;
        }

        let range = FloatRange {
            current: ranges[index].current,
            end: ranges[index].end,
            step: ranges[index].step,
        };

        for val in range {
            current.push(val);
            helper(ranges, index + 1, current, output, &vars);
            current.pop();
        }
    }

    let mut output = Vec::new();
    helper(ranges, 0, &mut Vec::new(), &mut output, &vars);
    output
}
