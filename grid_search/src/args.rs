use std::u8;

use clap::Parser;
use rayon;

#[derive(Parser, Debug)]
pub struct Options {
    #[arg(short, long, default_value_t = String::from(""))]
    pub config: String,

    #[arg(short, long, default_value_t = u8::MAX)]
    pub threads: u8,
}

pub fn get_opts() -> Options {
    let mut args = Options::try_parse().unwrap();

    if args.config == "" {
        args.config = String::from("config.json");
    }

    if args.threads == u8::MAX {
        args.threads = rayon::current_num_threads() as u8;
    }

    args
}
