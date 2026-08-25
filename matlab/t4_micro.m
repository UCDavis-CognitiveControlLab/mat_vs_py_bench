function t4_micro(n, reps)
% T4 -- language microbenchmark, MATLAB arm. Mirrors t4_micro.py exactly:
% same loop, same operations, same iteration count, no vectorisation.
%
% Ruling-out evidence only. See t4_micro.py for why this is not the argument.
%
%   t4_micro(1000000, 20)

    if nargin < 1, n    = 1000000; end
    if nargin < 2, reps = 20;      end

    branchLoop(floor(n/10));        % warm-up (also lets the JIT settle)

    ms = zeros(reps, 1);
    for r = 1:reps
        t0 = GetSecs;
        branchLoop(n);
        ms(r) = (GetSecs - t0) * 1000;
    end

    fprintf('T4  %d branch+arith iterations, %d reps\n', n, reps);
    printStats(ms);
    perIterNS = median(ms) * 1e6 / n;
    fprintf('\n  per iteration: %.1f ns\n', perIterNS);

    saveResult('t4_micro_matlab', ms, struct('n', n, 'reps', reps, ...
        'per_iter_ns', perIterNS));
end

function acc = branchLoop(n)
    acc = 0;
    for i = 0:(n-1)
        if mod(i, 3) == 0
            acc = acc + i;
        elseif mod(i, 5) == 0
            acc = acc - i;
        else
            acc = acc + 1;
        end
    end
end
