param(
    [int]$Count = 5,
    [string]$Prefix = "seed",
    [string]$Password = "seed12345",
    [switch]$Staff
)

$ErrorActionPreference = "Stop"

$argsList = @(
    "exec",
    "web",
    "python",
    "manage.py",
    "seed_interview_users",
    "--count",
    $Count,
    "--prefix",
    $Prefix,
    "--password",
    $Password
)

if ($Staff) {
    $argsList += "--staff"
}

docker compose @argsList
