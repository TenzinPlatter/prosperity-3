pub struct FloatRange {
    pub current: f64,
    pub end: f64,
    pub step: f64,
}

impl Iterator for FloatRange {
    type Item = f64;

    fn next(&mut self) -> Option<Self::Item> {
        if (self.step > 0. && self.current >= self.end)
            || (self.step < 0. && self.current <= self.end)
        {
            return None;
        }

        let res = self.current;
        self.current += self.step;
        Some(res)
    }
}

impl FloatRange {
    pub fn new(start: f64, end: f64, step: f64) -> FloatRange {
        FloatRange {
            current: start,
            end,
            step,
        }
    }
}
