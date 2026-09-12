<?php
include_once('./includes/headerNav.php');
?>
<head><style>
.sgn-input{width:300px;color:grey}.signup_div{display:flex;justify-content:center;align-items:center}.div-sign{text-align:center}.signup-form{display:grid;grid-template-columns:140px 300px;gap:10px;align-items:center}.signup-form .actions{grid-column:1 / -1;text-align:center}@media(max-width:600px){.signup-form{grid-template-columns:1fr;width:95%}.sgn-input{width:100%}}
</style></head>
<h3 style="color:brown;text-align:center"><ins>Please sign up</ins></h3>
<div class="signup_div">
<form class="signup-form" action="includes/signup.inc.php" method="post" autocomplete="on">
<label for="signup-name">Name:</label><input id="signup-name" class="sgn-input" type="text" name="name" required maxlength="100" autocomplete="name">
<label for="signup-email">Email:</label><input id="signup-email" class="sgn-input" type="email" name="email" required maxlength="254" autocomplete="email">
<label for="signup-address">Address:</label><input id="signup-address" class="sgn-input" type="text" name="address" required maxlength="500" autocomplete="street-address">
<label for="signup-phone">Phone:</label><input id="signup-phone" class="sgn-input" type="tel" name="number" required maxlength="20" inputmode="tel" autocomplete="tel" pattern="[0-9+()\-\s]{7,20}">
<label for="signup-password">Password:</label><input id="signup-password" class="sgn-input" type="password" name="pwd" required minlength="8" autocomplete="new-password">
<label for="signup-password-confirm">Re-Password:</label><input id="signup-password-confirm" class="sgn-input" type="password" name="rpwd" required minlength="8" autocomplete="new-password">
<div class="actions"><button type="submit" class="btn btn-large btn-info" name="submit">Register</button>
<?php if(isset($_GET['error'])): ?><br><br><div class="alert alert-danger"><?php $errors=['!loggedin'=>'Signup or Login first.','enterValidNumber'=>'Enter valid number.','invalidemail'=>'Enter valid email address.','pwdnotmatch'=>'Entered password does not match.','emptyInput'=>'Form must be filled.','emailAlreadytaken'=>'Account is already registered with this email.']; echo htmlspecialchars($errors[$_GET['error']] ?? 'Unable to register.', ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8'); ?></div><?php endif; ?></div>
</form></div>
<?php include_once('./includes/footer.php'); ?>
<script src="./js/jquery.js"></script><script src="./js/bootstrap.min.js"></script>