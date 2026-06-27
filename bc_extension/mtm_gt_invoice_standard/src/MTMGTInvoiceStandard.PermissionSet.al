permissionset 71100 "MTM GT INV STD"
{
    Assignable = true;
    Caption = 'MTM GT Invoice Standard';

    Permissions =
        tabledata "Company Information" = R,
        tabledata "Custom Report Selection" = RM,
        tabledata "Report Selections" = RM,
        tabledata "Tenant Report Layout Selection" = RIMD,
        codeunit "MTM GT Invoice Std. Mgt." = X,
        codeunit "MTM GT Invoice Std. Setup" = X,
        codeunit "MTM GT Invoice Std. Upgrade" = X,
        page "MTM GT Invoice Std. Setup" = X,
        report "MTM GT Draft Invoice" = X,
        report FacturaGTM = X;
}
