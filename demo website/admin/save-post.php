<?php
include_once('./includes/restriction.php'); // admin-only
include "includes/config.php";

$error = true;
$file_name = null;

//1st restriction or condition before it is going to be uploaded on database
//these are required for only pic upload
if(isset($_FILES['prod-img']) && $_FILES['prod-img']['error'] === UPLOAD_ERR_OK){
  $file_size = $_FILES['prod-img']['size'];
  $file_tmp  = $_FILES['prod-img']['tmp_name'];

  $extensions = array("jpeg","jpg","png");
  $tmp = explode('.', $_FILES['prod-img']['name']);
  $file_ext = strtolower(end($tmp));

  // Validate the ACTUAL image content, not just the filename extension,
  // to stop someone uploading a PHP script renamed to ".jpg".
  $imageInfo = @getimagesize($file_tmp);
  $allowedMime = ['image/jpeg', 'image/png'];

  if(in_array($file_ext, $extensions) === false || $imageInfo === false || !in_array($imageInfo['mime'], $allowedMime))
  {
    echo "This extension isn't allowed , please choose a jpg,jpeg or png file.";
    die();
  }
  else if($file_size >= 2097152){
    echo "file size must be less 2mb";
    die();
  }
  else{
    // Generate a random filename so it can never collide/overwrite an
    // existing file and can never contain path-traversal characters.
    $file_name = bin2hex(random_bytes(16)) . '.' . $file_ext;
    $error = !move_uploaded_file($file_tmp, __DIR__ . "/upload/" . $file_name);
  }
}//main if-end

//now finally if all condition good i.e error=false than save-post to database
   if($error === false){
    if (session_status() !== PHP_SESSION_ACTIVE) {
        session_start();
    }
    $today_date =  date("j,n,Y");
    $author = $_SESSION['customer_name'];

    $catag = $_POST['prod-category'];
    $title = $_POST['prod-title'];
    $price = $_POST['prod-price'];
    $desc = $_POST['prod-desc'];
    $noofitem = $_POST['noofitem'];

    $stmt = $conn->prepare("INSERT INTO products (product_catag,product_title,product_price,product_desc,product_date,product_img,product_left,product_author) VALUES (?,?,?,?,?,?,?,?)");
    $stmt->bind_param('ssdsssis', $catag, $title, $price, $desc, $today_date, $file_name, $noofitem, $author);
    $stmt->execute();
    $stmt->close();
    $conn->close();
    header("location:post.php?success");
    exit();
   }else{
     echo "Upload failed.";
   }
    ?>