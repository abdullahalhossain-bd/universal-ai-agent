<?php
$serverName = "localhost";
$dBUsername = "u752807333_ai";
$dBPassword = "Me1Boss1@";
$dBName = "u752807333_ai";

$conn = new mysqli($serverName, $dBUsername, $dBPassword, $dBName);

if ($conn->connect_error) {
    die("Connection failed: " . $conn->connect_error);
}
?>