function up --description 'Go up N directories (default 1)'
    set -l n (math max 1, (string match -r '^\d+$' -- $argv[1]; or echo 1))
    cd (string repeat -n $n ../)
end
