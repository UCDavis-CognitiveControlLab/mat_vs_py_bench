function printStats(x)
% Median and spread, matching report.py summarise().
% Median not mean: one dropped frame is a huge outlier that moves a mean around
% while saying nothing about typical behaviour.
    x = x(isfinite(x));
    fprintf('       n: %9.4f\n', numel(x));
    fprintf('  median: %9.4f\n', median(x));
    fprintf('    mean: %9.4f\n', mean(x));
    fprintf('      sd: %9.4f\n', std(x));
    fprintf('     iqr: %9.4f\n', iqr(x));
    fprintf('     p01: %9.4f\n', prctile(x, 1));
    fprintf('     p99: %9.4f\n', prctile(x, 99));
    fprintf('     min: %9.4f\n', min(x));
    fprintf('     max: %9.4f\n', max(x));
end
