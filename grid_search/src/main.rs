use grid_search::{
    args::get_opts, config::parse_config, create_or_clean_logs_dir, get_constant_strings,
    run::run_all,
};

use std::path::Path;

fn main() {
    let opts = get_opts();

    let cfg = parse_config(&opts.config).unwrap();

    let constant_strings = get_constant_strings(&cfg.variables);

    create_or_clean_logs_dir(&Path::new(&cfg.logs_dir), constant_strings.len());

    run_all(&constant_strings, &cfg, &opts).unwrap();
}
