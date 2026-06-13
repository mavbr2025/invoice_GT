permissionset 71000 "MTM CUST INV API"
{
    Assignable = true;
    Caption = 'MTM Customer Invoicing API';

    Permissions =
        tabledata Customer = R,
        tabledata "Custom Report Selection" = R,
        tabledata "Document Sending Profile" = R,
        tabledata "Report Layout Selection" = R,
        tabledata "Report Selections" = R,
        tabledata "Sales Invoice Header" = R,
        tabledata "Sales Invoice Line" = RM,
        codeunit GTMLeerDocumentos = X,
        codeunit "Fun. Factura GT" = X,
        codeunit "MTM GT Posted Inv FEL Mgt" = X,
        page "MTM Customer Invoicing API" = X,
        page "MTM Customer Layout Setup API" = X,
        page "MTM Custom Report Sel API" = X,
        page "MTM Doc Sending Profiles API" = X,
        page "MTM Posted Inv FEL Desc API" = X,
        page "MTM Report Layout List API" = X,
        page "MTM Report Layout Sel API" = X,
        page "MTM Report Selections API" = X;
}
