<?php
   // NOTE: restriction.php must NOT be included here. It exits/redirects
   // anyone who isn't already an authenticated admin, which would make the
   // login form itself unreachable. Access control belongs on the pages
   // *behind* the login, not on the login page.
?>
<!doctype html>
<html>
   <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta http-equiv="X-UA-Compatible" content="ie=edge">
        <title>ADMIN | Login</title>
        <link rel="stylesheet" href="../css/bootstrap.min.css" />
        <link rel="stylesheet" href="../css/style.php">
        <style>
            .container{
                position:absolute;
                top:70px;
                left:25%;
                width: 50%;
                display:flex;
                align-items:center;
                justify-content:center;
                height: 500px;
                background-color: whitesmoke;
            } 
        </style>
    </head>

    <body>
        <div id="wrapper-admin" class="body-content">
            <div class="container">
                <div class="row">
                    <div class="col-md-offset-4 col-md-4">
                       <h2 id="hlogo"><img src="../images/logo_admin.png" id="logo" alt=""></h2>
                        <h3 class="heading">Admin</h3>
                        <!-- Form Start -->
                        <div class="form">
                        <form  action="<?php $_SERVER['PHP_SELF']; ?>" method ="POST">
                            <div class="form-group">
                                <label>UserEmail</label>
                                <input class="input-admin" type="email" name="userEmail" class="form-control" placeholder="" required>
                            </div>
                            <div class="form-group">
                                <label>Password</label>
                                <input class="input-admin" type="password" name="password" class="form-control" placeholder="" required>
                            </div>
                            <input type="submit" name="login" class="btn btn-primary" value="login" />
                        </form>
                        <!-- /Form  End -->
                        </div>
                     
                        <?php 
                                    if (session_status() !== PHP_SESSION_ACTIVE) {
                                        session_start();
                                    }
                                    if(isset($_POST['login'])){
                                        include "includes/config.php";
                                        if(empty($_POST['userEmail']) || empty($_POST['password'])){
                                          echo '<div class="alert alert-danger">All Fields must be entered.</div>';
                                          die();
                                        }else{
                                          $email = $_POST['userEmail'];
                                          $password = $_POST['password'];

                                          // Prepared statement - prevents SQL injection
                                          $stmt = $conn->prepare("SELECT customer_id, customer_pwd, customer_role FROM customer WHERE customer_email = ? AND customer_role = 'admin'");
                                          $stmt->bind_param('s', $email);
                                          $stmt->execute();
                                          $result = $stmt->get_result();

                                          $row = $result->fetch_assoc();
                                          $passwordOk = false;
                                          if($row){
                                              // Supports both properly hashed passwords (password_hash)
                                              // and legacy plain-text rows already in the DB; legacy rows
                                              // are transparently upgraded to a hash on successful login.
                                              if(password_verify($password, $row['customer_pwd'])){
                                                  $passwordOk = true;
                                              } elseif(hash_equals($row['customer_pwd'], $password)){
                                                  $passwordOk = true;
                                                  $newHash = password_hash($password, PASSWORD_DEFAULT);
                                                  $upd = $conn->prepare("UPDATE customer SET customer_pwd = ? WHERE customer_id = ?");
                                                  $upd->bind_param('si', $newHash, $row['customer_id']);
                                                  $upd->execute();
                                                  $upd->close();
                                              }
                                          }

                                          if($passwordOk){
                                              session_regenerate_id(true);
                                              $_SESSION['logged-in'] = '1';
                                              $_SESSION['id'] = $row['customer_id'];
                                              $_SESSION['customer_role'] = $row['customer_role'];
                                              header("Location: ./post.php");
                                              exit();
                                          }else{
                                          echo '<div class="alert alert-danger">Username and Password are not matched.</div>';
                                        }
                                      }
                                      }
                        ?>

                    </div>
                </div>
            </div>
        </div>
    </body>
</html>